import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any, Literal

from sqlalchemy import func, select, update

from agent_api.agent.context import serialize_message
from agent_api.agent.loop import AgentRunner, Confirmation, SteeringInbox
from agent_api.agent.settings import AgentSettings
from agent_api.db import Database
from agent_api.models import AgentConfig, ChatSession, Message, Run, Step, utcnow
from agent_api.tools.files import FILE_TOOL_NAMES
from agent_api.tracing import serialize_run
from agent_api.uploads import AttachmentError, save_attachment
from agent_api.workspace import Workspace

_END = object()
HEARTBEAT_S = 15.0


class RunConflict(Exception):
    pass


class RunNotFound(Exception):
    pass


class EventStream:
    """单次运行的事件队列。运行在独立任务里执行，客户端断开不会中断运行。"""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[Any] = asyncio.Queue()

    async def emit(self, event: str, data: dict[str, Any]) -> None:
        await self._queue.put((event, data))

    def close(self) -> None:
        self._queue.put_nowait(_END)

    async def sse(self) -> AsyncIterator[str]:
        while True:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=HEARTBEAT_S)
            except TimeoutError:
                yield ": ping\n\n"
                continue
            if item is _END:
                return
            event, data = item
            yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


async def load_agent_settings(db: Database) -> AgentSettings:
    async with db.sessionmaker() as s:
        row = await s.get(AgentConfig, 1)
        return AgentSettings.model_validate(row.data if row else {})


class _LiveRun:
    def __init__(self, session_id: uuid.UUID, stream: EventStream, inbox: SteeringInbox) -> None:
        self.session_id = session_id
        self.stream = stream
        self.inbox = inbox


class RunManager:
    def __init__(self, db: Database, runner: AgentRunner) -> None:
        self.db = db
        self.runner = runner
        self._tasks: dict[uuid.UUID, asyncio.Task[None]] = {}
        self._live: dict[uuid.UUID, _LiveRun] = {}
        self._lock = asyncio.Lock()

    async def start(
        self,
        session_id: uuid.UUID,
        text: str,
        attachments: list[dict[str, str]] | None = None,
        skills: list[str] | None = None,
        effort: str | None = None,
        permission_mode: str | None = None,
    ) -> EventStream | dict[str, Any]:
        async with self._lock:
            return await self._start(
                session_id, text, attachments or [], skills or [], effort, permission_mode
            )

    async def _start(
        self,
        session_id: uuid.UUID,
        text: str,
        attachments: list[dict[str, str]],
        skills: list[str],
        effort: str | None = None,
        permission_mode: str | None = None,
    ) -> EventStream | dict[str, Any]:
        settings = await load_agent_settings(self.db)
        if effort in {"off", "low", "medium", "high", "max"}:
            settings = settings.model_copy(update={"thinking_effort": effort})
        async with self.db.sessionmaker() as s:
            session = await s.get(ChatSession, session_id)
            if session is None:
                raise RunNotFound("会话不存在")
            if permission_mode in {"ask", "assist", "full"}:
                session.permission_mode = permission_mode
            stored: list[dict] = []
            if attachments:
                if self.runner.upload_dir is None:
                    raise AttachmentError("服务没有配置文件目录")
                workspace = Workspace.open(self.runner.upload_dir, session_id)
                for item in attachments:
                    stored.append(
                        save_attachment(
                            workspace,
                            name=item["name"],
                            media_type=item.get("media_type") or "application/octet-stream",
                            data_base64=item["data_base64"],
                            allow_images=settings.image_input,
                        )
                    )
            active = await s.scalars(
                select(Run).where(
                    Run.session_id == session_id,
                    Run.status.in_(["running", "awaiting_confirmation"]),
                )
            )
            for prev in active:
                if prev.status == "running" and prev.id in self._tasks:
                    return await self._steer(s, prev, session, text, stored, skills)
                await self._supersede(s, prev)

            seq = (
                await s.scalar(
                    select(func.max(Message.seq)).where(Message.session_id == session_id)
                )
            ) or 0
            visible = text.strip()
            if not visible and not stored and skills:
                visible = "请按指定技能处理。"
            run = Run(
                session_id=session_id,
                input_text=visible or (stored[0]["name"] if stored else ""),
                config_snapshot=settings.snapshot_dict(),
            )
            s.add(run)
            await s.flush()
            user_msg = Message(
                session_id=session_id,
                run_id=run.id,
                seq=seq + 1,
                role="user",
                content=visible,
                attachments=stored or None,
                skill_names=skills or None,
            )
            s.add(user_msg)
            if seq == 0:
                title = visible or (stored[0]["name"] if stored else "")
                session.title = title.replace("\n", " ")[:40] or "新对话"
            session.updated_at = utcnow()
            await s.commit()

        stream = EventStream()
        await stream.emit(
            "run.started",
            {"run": serialize_run(run), "user_message": serialize_message(user_msg)},
        )
        self._spawn(run.id, session_id, stream, None)
        return stream

    async def confirm(
        self, run_id: uuid.UUID, tool_call_id: str, choice: Literal["once", "session", "reject"]
    ) -> EventStream:
        async with self.db.sessionmaker() as s:
            run = await s.get(Run, run_id)
            if run is None:
                raise RunNotFound("运行不存在")
            if run.status != "awaiting_confirmation":
                raise RunConflict(f"运行当前状态为 {run.status}，无法确认")
            run.status = "running"
            run.stop_reason = None
            await s.commit()

        stream = EventStream()
        await stream.emit("run.resumed", {"run": serialize_run(run)})
        self._spawn(
            run_id,
            run.session_id,
            stream,
            Confirmation(tool_call_id=tool_call_id, choice=choice),
        )
        return stream

    def cancel(self, run_id: uuid.UUID) -> bool:
        task = self._tasks.get(run_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    async def shutdown(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)

    def _spawn(
        self,
        run_id: uuid.UUID,
        session_id: uuid.UUID,
        stream: EventStream,
        confirmation: Confirmation | None,
    ) -> None:
        inbox = SteeringInbox()
        self._live[run_id] = _LiveRun(session_id, stream, inbox)

        async def _run() -> None:
            try:
                await self.runner.execute(run_id, stream.emit, confirmation, inbox)
            finally:
                self._tasks.pop(run_id, None)
                self._live.pop(run_id, None)
                stream.close()

        self._tasks[run_id] = asyncio.create_task(_run(), name=f"run-{run_id}")

    async def _steer(
        self,
        db_session,
        run: Run,
        session: ChatSession,
        text: str,
        attachments: list[dict],
        skills: list[str],
    ) -> dict[str, Any]:
        """运行还在进行时，把新消息挂到这次运行上，等当前这一轮结束后再插进去。"""
        live = self._live.get(run.id)
        if live is None:
            raise RunConflict("该会话已有运行中的任务")
        visible = text.strip()
        if not visible and not attachments and skills:
            visible = "请按指定技能处理。"
        async with live.inbox.lock:
            live.inbox.push(
                {
                    "content": visible,
                    "attachments": attachments or None,
                    "skill_names": skills or None,
                }
            )
        return {"queued": True}

    async def _supersede(self, s, prev: Run) -> None:
        """用户在等待确认时发了新消息：旧运行作废，待确认的调用视为未执行。"""
        prev.status = "cancelled"
        prev.stop_reason = "superseded"
        prev.ended_at = utcnow()
        await s.execute(
            update(Step)
            .where(Step.run_id == prev.id, Step.status == "pending")
            .values(status="cancelled", ended_at=utcnow())
        )


async def recover_interrupted_runs(db: Database) -> None:
    """进程重启后，内存里的任务已经不在了，把残留的「运行中」标记为失败。"""
    async with db.sessionmaker() as s:
        await s.execute(
            update(Run)
            .where(Run.status == "running")
            .values(status="failed", stop_reason="server_restart", error="服务重启，运行被中断")
        )
        await s.execute(update(Step).where(Step.status == "running").values(status="cancelled"))
        await s.commit()


async def relax_legacy_run_timeout(db: Database) -> None:
    """旧默认把整次运行卡在 120 秒。还没单独配过空闲超时的，改成 15 分钟后再收尾。"""
    async with db.sessionmaker() as s:
        row = await s.get(AgentConfig, 1)
        if row is None:
            return
        data = dict(row.data or {})
        if "stream_idle_s" in data or data.get("run_timeout_s") != 120:
            return
        data["run_timeout_s"] = 900
        row.data = data
        await s.commit()


async def enable_file_tools_once(db: Database) -> None:
    """已有配置里补上文件工具，只补一次，之后用户关掉会保留。"""
    async with db.sessionmaker() as s:
        row = await s.get(AgentConfig, 1)
        if row is None or (row.data or {}).get("file_tools_seeded"):
            return
        data = dict(row.data or {})
        if "enabled_tools" in data:
            tools = list(data["enabled_tools"])
            for name in FILE_TOOL_NAMES:
                if name not in tools:
                    tools.append(name)
            data["enabled_tools"] = tools
        data["file_tools_seeded"] = True
        row.data = data
        await s.commit()


async def enable_read_skill_once(db: Database) -> None:
    """已有配置里补上 read_skill，只补一次，之后用户关掉会保留。"""
    await _enable_tool_once(db, "read_skill", "read_skill_seeded")


async def enable_create_skill_once(db: Database) -> None:
    """已有配置里补上 create_skill，只补一次，之后用户关掉会保留。"""
    await _enable_tool_once(db, "create_skill", "create_skill_seeded")


async def _enable_tool_once(db: Database, tool_name: str, flag: str) -> None:
    async with db.sessionmaker() as s:
        row = await s.get(AgentConfig, 1)
        if row is None or (row.data or {}).get(flag):
            return
        data = dict(row.data or {})
        if "enabled_tools" in data and tool_name not in data["enabled_tools"]:
            data["enabled_tools"] = [*data["enabled_tools"], tool_name]
        data[flag] = True
        row.data = data
        await s.commit()
