import base64
import binascii
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import unquote
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from openai import APIConnectionError, APIStatusError
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.agent.context import serialize_message
from agent_api.agent.runs import EventStream, RunConflict, RunManager, RunNotFound
from agent_api.agent.settings import AgentSettings, normalize_api_base
from agent_api.config import get_settings
from agent_api.db import Database
from agent_api.llm import MODEL_CATALOG
from agent_api.llm.providers import (
    known_provider,
    provider_payload,
    reasoning_params,
    resolve_credentials,
)
from agent_api.models import AgentConfig, ChatSession, Message, Run, ScheduledTask, Step, utcnow
from agent_api.schedules import EFFORTS, REPEATS, apply_schedule, serialize_task
from agent_api.skills import builtin_names, find_in_catalog, load_catalog
from agent_api.skills.importer import SkillImportError, import_skill_zip
from agent_api.tools import ToolRegistry
from agent_api.tracing import serialize_run, serialize_step
from agent_api.tracing.recorder import iso_utc
from agent_api.uploads import AttachmentError
from agent_api.workspace import Workspace, WorkspaceError

router = APIRouter(prefix="/api")


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_manager(request: Request) -> RunManager:
    return request.app.state.runs


def get_registry(request: Request) -> ToolRegistry:
    return request.app.state.registry


async def get_session(db: Annotated[Database, Depends(get_db)]):
    async with db.sessionmaker() as s:
        yield s


DbSession = Annotated[AsyncSession, Depends(get_session)]
Manager = Annotated[RunManager, Depends(get_manager)]
Registry = Annotated[ToolRegistry, Depends(get_registry)]


def _sse(stream: EventStream) -> StreamingResponse:
    return StreamingResponse(
        stream.sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _serialize_session(s: ChatSession) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "title": s.title,
        "created_at": iso_utc(s.created_at),
        "updated_at": iso_utc(s.updated_at),
        "permission_mode": s.permission_mode or "assist",
    }


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    configured = settings.llm_provider == "mock" or bool(settings.dashscope_api_key)
    db: Database = request.app.state.db
    async with db.sessionmaker() as session:
        row = await session.get(AgentConfig, 1)
        if row is not None and AgentSettings.model_validate(row.data).api_key:
            configured = True
    return {
        "ok": True,
        "name": settings.agent_name,
        "llm_provider": settings.llm_provider,
        "llm_configured": configured,
    }


# ---------- 会话 ----------


@router.get("/sessions")
async def list_sessions(db: DbSession) -> list[dict[str, Any]]:
    rows = await db.scalars(select(ChatSession).order_by(ChatSession.updated_at.desc()).limit(200))
    return [_serialize_session(s) for s in rows]


@router.post("/sessions", status_code=201)
async def create_session(db: DbSession) -> dict[str, Any]:
    session = ChatSession()
    db.add(session)
    await db.commit()
    return _serialize_session(session)


@router.get("/sessions/{session_id}")
async def get_session_detail(session_id: uuid.UUID, db: DbSession) -> dict[str, Any]:
    session = await db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(404, "会话不存在")
    messages = await db.scalars(
        select(Message).where(Message.session_id == session_id).order_by(Message.seq)
    )
    runs = list(
        await db.scalars(select(Run).where(Run.session_id == session_id).order_by(Run.started_at))
    )
    pending: dict[str, Any] | None = None
    waiting = [r for r in runs if r.status == "awaiting_confirmation"]
    if waiting:
        step = await db.scalar(
            select(Step)
            .where(Step.run_id == waiting[-1].id, Step.status == "pending")
            .order_by(Step.seq.desc())
        )
        if step is not None:
            pending = {**(step.input or {}), "step_id": str(step.id)}
    return {
        "session": _serialize_session(session),
        "messages": [serialize_message(m) for m in messages],
        "runs": [serialize_run(r) for r in runs],
        "pending_confirmation": pending,
    }


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: uuid.UUID, db: DbSession, request: Request) -> None:
    run_ids = select(Run.id).where(Run.session_id == session_id)
    await db.execute(delete(Step).where(Step.run_id.in_(run_ids)))
    await db.execute(delete(Run).where(Run.session_id == session_id))
    await db.execute(delete(Message).where(Message.session_id == session_id))
    await db.execute(delete(ChatSession).where(ChatSession.id == session_id))
    await db.commit()
    root = getattr(request.app.state, "workspace_root", None)
    if root is not None:
        shutil.rmtree(Path(root) / str(session_id), ignore_errors=True)


class IncomingAttachment(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    media_type: str = Field("application/octet-stream", max_length=200)
    data_base64: str = Field(..., min_length=1)


class SendMessage(BaseModel):
    content: str = Field("", max_length=8000)
    attachments: list[IncomingAttachment] = Field(default_factory=list, max_length=4)
    skills: list[str] = Field(default_factory=list, max_length=8)
    permission_mode: Literal["ask", "assist", "full"] = "assist"

    @model_validator(mode="after")
    def has_payload(self) -> "SendMessage":
        if not self.content.strip() and not self.attachments and not self.skills:
            raise ValueError("请输入消息或添加附件")
        return self


def _catalog(request: Request):
    return load_catalog(
        getattr(request.app.state, "skills_dir", None),
        getattr(request.app.state, "user_skills_dir", None),
    )


async def _installed_names(db: AsyncSession, known: list[str]) -> list[str]:
    """用户从市场另行安装的技能名。没配过就是空，不把内置和全部市场技能算进去。"""
    row = await db.get(AgentConfig, 1)
    saved = (row.data or {}).get("installed_skills") if row is not None else None
    if not isinstance(saved, list):
        return []
    return [name for name in saved if name in known]


def _personally_installed(skill, opted: set[str]) -> bool:
    if skill.source == "builtin":
        return False
    if skill.source == "user":
        return True
    return skill.name in opted


async def _write_installed(db: AsyncSession, names: list[str]) -> None:
    row = await db.get(AgentConfig, 1)
    if row is None:
        row = AgentConfig(id=1, data={})
        db.add(row)
    data = dict(row.data or {})
    data["installed_skills"] = names
    row.data = data
    row.updated_at = utcnow()
    await db.commit()


def _selected_skills(request: Request, names: list[str], installed: set[str]) -> list[str]:
    builtin = getattr(request.app.state, "skills_dir", None)
    user = getattr(request.app.state, "user_skills_dir", None)
    chosen: list[str] = []
    for name in names:
        if name in chosen:
            continue
        skill = find_in_catalog(builtin, user, name)
        if skill is None:
            raise HTTPException(422, f"没有名为 {name} 的技能")
        if skill.source == "market" and name not in installed:
            raise HTTPException(422, f"技能 {name} 还没有安装")
        chosen.append(name)
    return chosen


def _skill_brief(skill, installed: set[str]) -> dict[str, Any]:
    return {
        "name": skill.name,
        "title": skill.title,
        "description": skill.description,
        "source": skill.source,
        "installed": _personally_installed(skill, installed),
    }


@router.get("/skills")
async def list_skills(request: Request, db: DbSession) -> dict[str, Any]:
    skills = _catalog(request)
    installed = set(await _installed_names(db, [skill.name for skill in skills]))
    return {"skills": [_skill_brief(skill, installed) for skill in skills]}


class ImportSkillRequest(BaseModel):
    filename: str = Field("", max_length=200)
    data_base64: str = Field(..., min_length=1)
    install: bool = True


@router.post("/skills/import")
async def import_skill(body: ImportSkillRequest, request: Request, db: DbSession) -> dict[str, Any]:
    try:
        data = base64.b64decode(body.data_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(422, "压缩包内容无法解析") from error
    user_root = getattr(request.app.state, "user_skills_dir", None)
    if user_root is None:
        raise HTTPException(422, "没有配置用户技能目录")
    try:
        skill = import_skill_zip(data, user_root)
    except SkillImportError as error:
        raise HTTPException(422, str(error)) from error
    if skill.name in builtin_names(getattr(request.app.state, "skills_dir", None)):
        shutil.rmtree(user_root / skill.name, ignore_errors=True)
        raise HTTPException(422, "这个名字是内置技能，不能作为外部技能安装")
    skills = _catalog(request)
    names = await _installed_names(db, [item.name for item in skills])
    if body.install and skill.name not in names:
        names.append(skill.name)
        await _write_installed(db, names)
    return {"name": skill.name, "title": skill.title, "installed": skill.name in names}


@router.get("/skills/{name}")
async def get_skill(name: str, request: Request, db: DbSession) -> dict[str, Any]:
    skills = _catalog(request)
    skill = next((item for item in skills if item.name == name), None)
    if skill is None:
        raise HTTPException(404, "技能不存在")
    installed = set(await _installed_names(db, [item.name for item in skills]))
    return {**_skill_brief(skill, installed), "body": skill.body}


@router.post("/skills/{name}/install")
async def install_skill(name: str, request: Request, db: DbSession) -> dict[str, Any]:
    skills = _catalog(request)
    skill = next((item for item in skills if item.name == name), None)
    if skill is None:
        raise HTTPException(404, "技能不存在")
    if skill.source != "market":
        raise HTTPException(422, "内置技能注册就有，不用再安装")
    names = await _installed_names(db, [item.name for item in skills])
    if name not in names:
        names.append(name)
    await _write_installed(db, names)
    return {"installed": names}


@router.post("/skills/{name}/remove")
async def remove_user_skill(name: str, request: Request, db: DbSession) -> dict[str, Any]:
    skills = _catalog(request)
    skill = next((item for item in skills if item.name == name and item.source == "user"), None)
    if skill is None:
        raise HTTPException(422, "只能移除外部安装的技能")
    user_root = getattr(request.app.state, "user_skills_dir", None)
    if user_root is not None:
        shutil.rmtree(user_root / name, ignore_errors=True)
    known = [item.name for item in _catalog(request)]
    names = [item for item in await _installed_names(db, known) if item != name]
    await _write_installed(db, names)
    return {"removed": name}


@router.post("/skills/{name}/uninstall")
async def uninstall_skill(name: str, request: Request, db: DbSession) -> dict[str, Any]:
    skills = _catalog(request)
    known = [skill.name for skill in skills]
    if name not in known:
        raise HTTPException(404, "技能不存在")
    names = [item for item in await _installed_names(db, known) if item != name]
    await _write_installed(db, names)
    return {"installed": names}


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: uuid.UUID,
    body: SendMessage,
    manager: Manager,
    request: Request,
    db: DbSession,
):
    try:
        result = await manager.start(
            session_id,
            body.content,
            [item.model_dump() for item in body.attachments],
            _selected_skills(
                request,
                body.skills,
                set(await _installed_names(db, [skill.name for skill in _catalog(request)])),
            ),
            permission_mode=body.permission_mode,
        )
    except RunNotFound as e:
        raise HTTPException(404, str(e)) from e
    except RunConflict as e:
        raise HTTPException(409, str(e)) from e
    except AttachmentError as e:
        raise HTTPException(422, str(e)) from e
    if isinstance(result, EventStream):
        return _sse(result)
    return result


def _workspace(request: Request, session_id: uuid.UUID) -> Workspace:
    root = getattr(request.app.state, "workspace_root", None)
    if root is None:
        raise HTTPException(404, "没有文件目录")
    return Workspace.open(Path(root), session_id)


@router.get("/sessions/{session_id}/files")
async def list_session_files(
    session_id: uuid.UUID, request: Request, db: DbSession
) -> dict[str, Any]:
    if await db.get(ChatSession, session_id) is None:
        raise HTTPException(404, "会话不存在")
    workspace = _workspace(request, session_id)
    if not workspace.root.exists():
        return {"files": []}
    files: list[dict[str, Any]] = []
    for zone in ("uploads", "workspace", "outputs"):
        try:
            entries = workspace.list_dir(f"/{zone}")
        except WorkspaceError:
            continue
        for entry in entries:
            if entry["kind"] == "file":
                files.append({**entry, "zone": zone})
    return {"files": files}


@router.get("/sessions/{session_id}/files/content")
async def download_session_file(
    session_id: uuid.UUID, request: Request, db: DbSession, path: str = Query(min_length=1)
) -> FileResponse:
    if await db.get(ChatSession, session_id) is None:
        raise HTTPException(404, "会话不存在")
    workspace = _workspace(request, session_id)
    try:
        located = workspace.locate(unquote(path))
    except WorkspaceError as e:
        raise HTTPException(404, str(e)) from e
    if located.denied or located.outside or not located.path.is_file():
        raise HTTPException(404, "文件不存在")
    return FileResponse(located.path, filename=located.path.name)


# ---------- 运行 ----------


class ConfirmBody(BaseModel):
    tool_call_id: str
    approved: bool | None = None
    choice: Literal["once", "session", "reject"] | None = None

    @model_validator(mode="after")
    def has_choice(self) -> "ConfirmBody":
        if self.choice is None and self.approved is None:
            raise ValueError("请选择本次允许、本对话允许或拒绝")
        return self

    def resolved(self) -> Literal["once", "session", "reject"]:
        if self.choice is not None:
            return self.choice
        return "once" if self.approved else "reject"


@router.post("/runs/{run_id}/confirm")
async def confirm_tool_call(run_id: uuid.UUID, body: ConfirmBody, manager: Manager):
    try:
        stream = await manager.confirm(run_id, body.tool_call_id, body.resolved())
    except RunNotFound as e:
        raise HTTPException(404, str(e)) from e
    except RunConflict as e:
        raise HTTPException(409, str(e)) from e
    return _sse(stream)


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: uuid.UUID, manager: Manager) -> dict[str, bool]:
    return {"cancelled": manager.cancel(run_id)}


@router.get("/runs")
async def list_runs(
    db: DbSession,
    status: str | None = None,
    session_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    query = select(Run, ChatSession.title).join(ChatSession, ChatSession.id == Run.session_id)
    count = select(func.count(Run.id))
    if status:
        query = query.where(Run.status == status)
        count = count.where(Run.status == status)
    if session_id:
        query = query.where(Run.session_id == session_id)
        count = count.where(Run.session_id == session_id)
    rows = await db.execute(query.order_by(Run.started_at.desc()).limit(limit).offset(offset))
    return {
        "total": await db.scalar(count),
        "items": [
            {
                **serialize_run(run),
                "session_title": title,
                "config_snapshot": {"model": run.config_snapshot.get("model")},
            }
            for run, title in rows
        ],
    }


@router.get("/runs/{run_id}")
async def get_run(run_id: uuid.UUID, db: DbSession) -> dict[str, Any]:
    run = await db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "运行不存在")
    steps = await db.scalars(select(Step).where(Step.run_id == run_id).order_by(Step.seq))
    return {"run": serialize_run(run), "steps": [serialize_step(s) for s in steps]}


# ---------- 智能体配置 / 工具 / 模型 ----------


@router.get("/agent-config")
async def get_agent_config(db: DbSession) -> dict[str, Any]:
    row = await db.get(AgentConfig, 1)
    current = AgentSettings.model_validate(row.data if row else {})
    return {
        "config": current.public_dict(),
        "defaults": AgentSettings().public_dict(),
        "updated_at": iso_utc(row.updated_at) if row else None,
    }


@router.put("/agent-config")
async def update_agent_config(
    body: AgentSettings, db: DbSession, registry: Registry
) -> dict[str, Any]:
    unknown = set(body.enabled_tools) - set(registry.names())
    if unknown:
        raise HTTPException(422, f"未知工具：{', '.join(sorted(unknown))}")
    row = await db.get(AgentConfig, 1)
    stored = AgentSettings.model_validate(row.data) if row else None
    if not body.api_key and stored is not None:
        body.api_key = stored.api_key
    if row is None:
        row = AgentConfig(id=1, data={})
        db.add(row)
    data = body.model_dump()
    if row.data and row.data.get("file_tools_seeded"):
        data["file_tools_seeded"] = True
    if row.data and row.data.get("read_skill_seeded"):
        data["read_skill_seeded"] = True
    if row.data and row.data.get("create_skill_seeded"):
        data["create_skill_seeded"] = True
    if isinstance((row.data or {}).get("installed_skills"), list):
        data["installed_skills"] = row.data["installed_skills"]
    row.data = data
    row.updated_at = utcnow()
    await db.commit()
    saved = AgentSettings.model_validate(data)
    return {"config": saved.public_dict(), "updated_at": iso_utc(row.updated_at)}


class ModelTestRequest(BaseModel):
    provider: str = "dashscope"
    api_base: str = ""
    api_key: str = ""
    model: str = Field(..., min_length=1, max_length=128)
    thinking: bool = False


@router.post("/model-config/test")
async def test_model_connection(body: ModelTestRequest, db: DbSession) -> dict[str, Any]:
    if not known_provider(body.provider):
        raise HTTPException(422, "未知的模型供应商")
    key = body.api_key.strip()
    if not key:
        row = await db.get(AgentConfig, 1)
        if row is not None:
            stored = AgentSettings.model_validate(row.data)
            if stored.provider == body.provider:
                key = stored.api_key
    base = normalize_api_base(body.api_base)
    key, base = resolve_credentials(provider=body.provider, api_base=base, api_key=key)
    if not key:
        raise HTTPException(400, "请填写 API Key")
    if not base:
        raise HTTPException(400, "请填写接口地址")
    effort = "high" if body.thinking else "off"
    extra = reasoning_params(body.model.strip(), effort, body.provider, base)
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=key, base_url=base, timeout=20)
        await client.chat.completions.create(
            model=body.model.strip(),
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            **({"extra_body": extra} if extra else {}),
        )
    except APIStatusError as error:
        message = error.message if hasattr(error, "message") else str(error)
        raise HTTPException(400, f"连接失败：{message[:180]}") from error
    except APIConnectionError as error:
        raise HTTPException(400, "连接失败：无法访问接口地址") from error
    except Exception as error:  # noqa: BLE001
        raise HTTPException(400, f"连接失败：{error.__class__.__name__}") from error
    return {"ok": True}


@router.get("/tools")
async def list_tools(registry: Registry) -> list[dict[str, Any]]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "parameters": t.schema()["function"]["parameters"],
            "requires_confirmation": t.requires_confirmation,
            "timeout_s": t.timeout_s,
            "example": t.example,
            "probes": t.probes,
        }
        for t in registry.all()
    ]


@router.get("/providers")
async def list_providers() -> list[dict[str, Any]]:
    return provider_payload()


@router.get("/models")
async def list_models() -> list[dict[str, Any]]:
    return [
        {
            "id": m.id,
            "label": m.label,
            "description": m.description,
            "input_price": m.input_price,
            "output_price": m.output_price,
        }
        for m in MODEL_CATALOG
    ]


@router.get("/usage/today")
async def usage_today(db: DbSession) -> dict[str, Any]:
    tz = ZoneInfo(get_settings().display_timezone)
    start_local = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    # 转成 UTC 再比较：SQLite 存的是不带时区的 UTC 时间
    start = start_local.astimezone(UTC)
    end = start + timedelta(days=1)
    row = (
        await db.execute(
            select(
                func.count(Run.id),
                func.coalesce(func.sum(Run.input_tokens), 0),
                func.coalesce(func.sum(Run.output_tokens), 0),
                func.coalesce(func.sum(Run.cost_cny), 0.0),
            ).where(Run.started_at >= start, Run.started_at < end)
        )
    ).one()
    return {
        "runs": row[0],
        "input_tokens": row[1],
        "output_tokens": row[2],
        "cost_cny": float(row[3]),
    }


# ---------- 定时任务 ----------


class ScheduleBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    prompt: str = Field(..., min_length=1, max_length=8000)
    effort: str = "high"
    repeat: str = "daily"
    interval_minutes: int = Field(60, ge=5, le=7 * 24 * 60)
    hour: int = Field(9, ge=0, le=23)
    minute: int = Field(0, ge=0, le=59)
    second: int = Field(0, ge=0, le=59)
    weekday: int = Field(0, ge=0, le=6)
    weekdays: list[int] = Field(default_factory=list)
    month_day: int = Field(1, ge=1, le=31)
    month: int = Field(1, ge=1, le=12)
    once_on: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    notify_wechat: bool = False
    enabled: bool = True

    @model_validator(mode="after")
    def known_choices(self) -> "ScheduleBody":
        if self.repeat not in REPEATS:
            raise ValueError("未知的重复方式")
        if self.effort not in EFFORTS:
            raise ValueError("未知的推理等级")
        for label, value in (("开始日期", self.valid_from), ("结束日期", self.valid_until)):
            if value:
                try:
                    datetime.fromisoformat(value)
                except ValueError as e:
                    raise ValueError(f"{label}格式应为 YYYY-MM-DD") from e
        if self.valid_from and self.valid_until and self.valid_from > self.valid_until:
            raise ValueError("有效期的开始不能晚于结束")
        if self.once_on:
            try:
                datetime.fromisoformat(self.once_on)
            except ValueError as e:
                raise ValueError("单次日期格式应为 YYYY-MM-DD") from e
        if any(day < 0 or day > 6 for day in self.weekdays):
            raise ValueError("星期超出范围")
        return self


def _fill_task(task: ScheduledTask, body: ScheduleBody) -> None:
    data = body.model_dump()
    if data["weekdays"]:
        data["weekday"] = min(data["weekdays"])
    for key, value in data.items():
        setattr(task, key, value)
    task.updated_at = utcnow()
    apply_schedule(task)


@router.get("/schedules")
async def list_schedules(db: DbSession) -> list[dict[str, Any]]:
    rows = await db.scalars(select(ScheduledTask).order_by(ScheduledTask.created_at.desc()))
    return [serialize_task(task) for task in rows]


@router.post("/schedules", status_code=201)
async def create_schedule(body: ScheduleBody, db: DbSession) -> dict[str, Any]:
    task = ScheduledTask(name=body.name.strip(), prompt=body.prompt.strip())
    _fill_task(task, body)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return serialize_task(task)


@router.patch("/schedules/{task_id}")
async def update_schedule(task_id: uuid.UUID, body: ScheduleBody, db: DbSession) -> dict[str, Any]:
    task = await db.get(ScheduledTask, task_id)
    if task is None:
        raise HTTPException(404, "定时任务不存在")
    _fill_task(task, body)
    await db.commit()
    await db.refresh(task)
    return serialize_task(task)


@router.delete("/schedules/{task_id}", status_code=204)
async def delete_schedule(task_id: uuid.UUID, db: DbSession) -> None:
    task = await db.get(ScheduledTask, task_id)
    if task is None:
        raise HTTPException(404, "定时任务不存在")
    await db.delete(task)
    await db.commit()
