"""智能体主循环：模型决定 → 护栏判定 → 工具执行 → 结果回填，直到给出最终回复或暂停。"""

import asyncio
import contextlib
import json
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, NoReturn

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.agent.context import PRUNE_NOTE, prune_history, serialize_message, to_llm_messages
from agent_api.agent.guardrails import Guardrails
from agent_api.agent.settings import AgentSettings
from agent_api.config import Settings, get_settings
from agent_api.db import Database
from agent_api.llm import LLMClient, LLMRequest, LLMResult, TextDelta, ThinkingDelta, estimate_cost
from agent_api.llm.providers import require_credentials, resolve_credentials
from agent_api.models import AgentConfig, ChatSession, Message, Run, Step
from agent_api.skills import Skill, load_catalog
from agent_api.tools import ToolContext, ToolError, ToolRegistry
from agent_api.tools.files import FILE_GUIDE, FILE_TOOL_NAMES
from agent_api.tracing import TraceExporter, TraceRecorder
from agent_api.tracing.recorder import Emit
from agent_api.uploads import redact_llm_messages
from agent_api.workspace import Workspace, allow_outside

MAX_STEPS_NOTE = (
    "【系统提示】本次运行已达到最大步数，不能再调用工具。"
    "请根据已有信息直接回复用户，并说明还没完成的部分。"
)
FAILURES_NOTE = (
    "【系统提示】工具已连续多次失败，不能再调用工具。请向用户如实说明失败情况和可能的原因。"
)
TIME_BUDGET_NOTE = (
    "【系统提示】本次运行时间已经比较长，不能再调用工具。"
    "请根据已有信息直接回复用户，并说明还没完成的部分。"
)
THINKING_NOTE = "思考过程必须使用简体中文，不要用英文展开推理。"


def _skill_note(installed: list[Skill], history: list[Message]) -> str:
    if not installed:
        return ""
    lines = ["可用技能：需要时调用 read_skill 读取全文，再按其中的步骤做。"]
    for skill in installed:
        lines.append(f"- {skill.name}：{skill.description}")
    chosen = _selected_skills(installed, history)
    if not chosen:
        return "\n".join(lines)
    blocks = ["【本轮指定技能】用户指定使用下面的技能，优先按这些说明做。"]
    for skill in chosen:
        blocks.append(f"## {skill.title}\n\n{skill.body}")
    return "\n".join(lines) + "\n\n" + "\n\n".join(blocks)


def _selected_skills(installed: list[Skill], history: list[Message]) -> list[Skill]:
    last_user = next((item for item in reversed(history) if item.role == "user"), None)
    if last_user is None or not last_user.skill_names:
        return []
    by_name = {skill.name: skill for skill in installed}
    return [by_name[name] for name in last_user.skill_names if name in by_name]


@dataclass(frozen=True)
class Confirmation:
    tool_call_id: str
    choice: Literal["once", "session", "reject"]

    @property
    def approved(self) -> bool:
        return self.choice != "reject"


class SteeringInbox:
    """运行中的插话。一次只取出一条，让模型先回应再看下一条。"""

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self._items: list[dict[str, Any]] = []

    def push(self, item: dict[str, Any]) -> None:
        self._items.append(item)

    def pending(self) -> bool:
        return bool(self._items)

    def drain_one(self) -> dict[str, Any] | None:
        if not self._items:
            return None
        return self._items.pop(0)


@dataclass
class _RunState:
    db: AsyncSession
    run: Run
    settings: AgentSettings
    recorder: TraceRecorder
    guard: Guardrails
    ctx: ToolContext
    history: list[Message]
    emit: Emit
    inbox: SteeringInbox | None = None
    started: float = field(default_factory=time.monotonic)
    consecutive_failures: int = 0
    partial_text: list[str] = field(default_factory=list)
    partial_reasoning: list[str] = field(default_factory=list)


class _PauseMark:
    """这个工具要等用户确认，先把前面已经准备好的工具跑完。"""


_PAUSE = _PauseMark()


@dataclass
class _ReadyTool:
    tc: dict[str, str]
    tool: Any
    args: Any
    attrs: dict[str, Any]
    permit_outside: bool = False


class _Paused(Exception):
    """有工具调用在等待用户确认，本段执行到此为止。"""


class _StreamIdle(Exception):
    """模型流在空闲时限内没有任何新输出。"""

    def __init__(self, had_text: bool) -> None:
        self.had_text = had_text


async def _next_llm_event(agen: AsyncIterator[Any], idle_s: float) -> Any | None:
    """取下一个流事件。流结束返回 None；超过 idle_s 没有新事件则抛出 TimeoutError。"""
    task = asyncio.ensure_future(agen.__anext__())
    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout=idle_s)
    except TimeoutError:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration):
            await task
        raise
    except StopAsyncIteration:
        return None


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


class AgentRunner:
    def __init__(
        self,
        db: Database,
        llm: LLMClient,
        registry: ToolRegistry,
        exporter: TraceExporter,
        upload_dir: Path | None = None,
        skills_dir: Path | None = None,
        user_skills_dir: Path | None = None,
        environment: Settings | None = None,
    ) -> None:
        self.db = db
        self.llm = llm
        self.registry = registry
        self.exporter = exporter
        self.upload_dir = upload_dir
        self.skills_dir = skills_dir
        self.user_skills_dir = user_skills_dir
        self.environment = environment or get_settings()

    async def execute(
        self,
        run_id: uuid.UUID,
        emit: Emit,
        confirmation: Confirmation | None = None,
        inbox: SteeringInbox | None = None,
    ) -> None:
        async with self.db.sessionmaker() as db:
            run = await db.get(Run, run_id)
            if run is None:
                return
            settings = AgentSettings.model_validate(run.config_snapshot)
            stored = await db.get(AgentConfig, 1)
            if stored is not None:
                current = AgentSettings.model_validate(stored.data)
                _, current_base = resolve_credentials(
                    provider=current.provider, api_base=current.api_base, api_key="",
                    settings=self.environment,
                )
                _, run_base = resolve_credentials(
                    provider=settings.provider, api_base=settings.api_base, api_key="",
                    settings=self.environment,
                )
                if current.provider == settings.provider and current_base == run_base:
                    settings.api_key = current.api_key
            recorder = TraceRecorder(db, run, emit, self.exporter)
            last_seq = await db.scalar(select(func.max(Step.seq)).where(Step.run_id == run_id))
            recorder.init_seq(last_seq or 0)
            history = list(
                await db.scalars(
                    select(Message)
                    .where(Message.session_id == run.session_id)
                    .order_by(Message.seq)
                )
            )
            workspace = None
            if self.upload_dir is not None:
                workspace = Workspace.open(self.upload_dir, run.session_id)
            chat = await db.get(ChatSession, run.session_id)
            grants = set((chat.permission_grants or []) if chat is not None else [])
            mode = chat.permission_mode if chat is not None else "assist"
            state = _RunState(
                db=db,
                run=run,
                settings=settings,
                recorder=recorder,
                guard=Guardrails(settings.enabled_tools, grants, mode),
                ctx=ToolContext(
                    session_id=run.session_id,
                    run_id=run.id,
                    workspace=workspace,
                    skills_dir=self.skills_dir,
                    user_skills_dir=self.user_skills_dir,
                    installed_skills=settings.installed_skills,
                ),
                history=history,
                emit=emit,
                inbox=inbox,
            )
            try:
                require_credentials(
                    provider=settings.provider, api_base=settings.api_base,
                    api_key=settings.api_key, settings=self.environment,
                )
                if confirmation is not None:
                    await self._process_pending_tool_calls(state, confirmation)
                await self._loop(state)
            except _Paused:
                await recorder.finish_run(
                    "awaiting_confirmation", stop_reason="confirmation_required"
                )
            except _StreamIdle as stalled:
                if stalled.had_text:
                    await recorder.finish_run("completed", stop_reason="stream_idle")
                else:
                    await recorder.finish_run(
                        "failed",
                        stop_reason="stream_idle",
                        error=f"模型超过 {settings.stream_idle_s} 秒没有新输出",
                    )
            except asyncio.CancelledError:
                await self._close_open_step(state, "cancelled", "用户取消")
                await recorder.finish_run("cancelled", stop_reason="user_cancelled")
            except Exception as e:  # noqa: BLE001  # 任何异常都要落成一次失败的运行
                await db.rollback()
                await self._close_open_step(state, "error", str(e))
                await recorder.finish_run("failed", stop_reason="error", error=str(e))

    def _available_skills(self, s: _RunState) -> list[Skill]:
        """内置技能人人都有。市场上的技能要单独安装后才交给模型。外部安装的技能直接可用。"""
        skills = load_catalog(self.skills_dir, self.user_skills_dir)
        opted = set(s.settings.installed_skills or [])
        chosen: dict[str, Skill] = {}
        for skill in skills:
            if skill.source == "builtin" or skill.source == "user" or skill.name in opted:
                chosen[skill.name] = skill
        return list(chosen.values())

    def _over_budget(self, s: _RunState) -> bool:
        return time.monotonic() - s.started >= s.settings.run_timeout_s

    async def _finish_on_budget(self, s: _RunState) -> None:
        limit = s.settings.run_timeout_s
        await self._guardrail_stop(s, "run_timeout", f"运行已超过 {limit} 秒，停止继续调用工具")
        result = await self._call_llm(s, with_tools=False, note=TIME_BUDGET_NOTE)
        if result.content.strip():
            await s.recorder.finish_run("completed", stop_reason="run_timeout")
            return
        await s.recorder.finish_run(
            "failed",
            stop_reason="run_timeout",
            error=f"运行超过 {limit} 秒，且没有形成回复",
        )

    async def _loop(self, s: _RunState) -> None:
        while True:
            if s.run.llm_calls >= s.settings.max_steps:
                await self._guardrail_stop(s, "max_steps", f"已达到最大步数 {s.settings.max_steps}")
                await self._call_llm(s, with_tools=False, note=MAX_STEPS_NOTE)
                await s.recorder.finish_run("completed", stop_reason="max_steps")
                return
            if self._over_budget(s):
                await self._finish_on_budget(s)
                return

            result = await self._call_llm(s, with_tools=True)
            if not result.tool_calls:
                if await self._absorb_steering(s):
                    continue
                await s.recorder.finish_run("completed", stop_reason="final_answer")
                return

            await self._process_pending_tool_calls(s, None)
            if await self._absorb_steering(s):
                continue

            if s.consecutive_failures >= s.settings.max_consecutive_failures:
                await self._guardrail_stop(
                    s, "consecutive_failures", f"工具已连续失败 {s.consecutive_failures} 次"
                )
                await self._call_llm(s, with_tools=False, note=FAILURES_NOTE)
                await s.recorder.finish_run("failed", stop_reason="consecutive_tool_failures")
                return

    async def _call_llm(self, s: _RunState, *, with_tools: bool, note: str = "") -> LLMResult:
        system_prompt = (
            f"{s.settings.system_prompt}\n\n{note}" if note else s.settings.system_prompt
        )
        if any(name in s.settings.enabled_tools for name in FILE_TOOL_NAMES):
            system_prompt = f"{system_prompt}\n{FILE_GUIDE}"
        if s.settings.thinking_effort != "off":
            system_prompt = f"{system_prompt}\n\n{THINKING_NOTE}"
        history, omitted = prune_history(s.history)
        skill_note = _skill_note(self._available_skills(s), history)
        if skill_note:
            system_prompt = f"{system_prompt}\n\n{skill_note}"
        if omitted:
            system_prompt = f"{system_prompt}\n\n{PRUNE_NOTE}"
        messages = to_llm_messages(
            system_prompt,
            history,
            include_images=s.settings.image_input,
            workspace_root=self.upload_dir,
        )
        traced = redact_llm_messages(messages)
        use_tools = with_tools and s.settings.tool_calling
        tools = self.registry.schemas(s.settings.enabled_tools) if use_tools else []
        step = await s.recorder.start(
            "llm_call",
            s.settings.model,
            input={"messages": traced, "tools": [t["function"]["name"] for t in tools]},
            attributes={
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": s.settings.provider,
                "gen_ai.request.model": s.settings.model,
                "gen_ai.request.temperature": s.settings.temperature,
            },
        )
        key, base = require_credentials(
            provider=s.settings.provider,
            api_base=s.settings.api_base,
            api_key=s.settings.api_key,
            settings=self.environment,
        )
        request = LLMRequest(
            model=s.settings.model,
            messages=messages,
            tools=tools,
            temperature=s.settings.temperature,
            api_key=key,
            base_url=base,
            provider=s.settings.provider,
            max_tokens=s.settings.max_output_tokens,
            thinking_effort=s.settings.thinking_effort,
            custom_protocol=s.settings.custom_protocol,
        )
        s.partial_text = []
        s.partial_reasoning = []
        result = await self._read_llm_stream(s, step, request)
        s.partial_text = []
        s.partial_reasoning = []

        await s.recorder.end(
            step,
            "ok",
            output={
                "content": result.content,
                "reasoning": result.reasoning,
                "tool_calls": [tc.to_dict() for tc in result.tool_calls],
                "finish_reason": result.finish_reason,
            },
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost_cny=(
                estimate_cost(s.settings.model, result.input_tokens, result.output_tokens)
                if self.llm.priced
                else 0.0
            ),
            attributes={
                "gen_ai.response.model": result.response_model,
                "gen_ai.response.finish_reasons": [result.finish_reason],
                "gen_ai.usage.input_tokens": result.input_tokens,
                "gen_ai.usage.output_tokens": result.output_tokens,
            },
        )
        await self._append_message(
            s,
            role="assistant",
            content=result.content,
            reasoning=result.reasoning or None,
            tool_calls=[tc.to_dict() for tc in result.tool_calls] or None,
        )
        return result

    async def _read_llm_stream(self, s: _RunState, step: Step, request: LLMRequest) -> LLMResult:
        result: LLMResult | None = None
        agen = self.llm.stream(request).__aiter__()
        try:
            while True:
                try:
                    event = await _next_llm_event(agen, s.settings.stream_idle_s)
                except TimeoutError:
                    await self._stall_llm_stream(s, step)
                if event is None:
                    break
                if isinstance(event, ThinkingDelta):
                    s.partial_reasoning.append(event.text)
                    await s.emit(
                        "message.thinking", {"run_id": str(s.run.id), "text": event.text}
                    )
                elif isinstance(event, TextDelta):
                    s.partial_text.append(event.text)
                    await s.emit("message.delta", {"run_id": str(s.run.id), "text": event.text})
                else:
                    result = event
        finally:
            with contextlib.suppress(RuntimeError):
                await agen.aclose()
        if result is None:
            raise RuntimeError("模型流结束但没有返回结果")
        return result

    async def _stall_llm_stream(self, s: _RunState, step: Step) -> NoReturn:
        await s.recorder.end(step, "timeout", error="模型流空闲超时")
        had_text = bool("".join(s.partial_text).strip())
        if s.partial_text or s.partial_reasoning:
            await self._append_message(
                s,
                role="assistant",
                content="".join(s.partial_text),
                reasoning="".join(s.partial_reasoning) or None,
            )
        s.partial_text = []
        s.partial_reasoning = []
        raise _StreamIdle(had_text)

    async def _absorb_steering(self, s: _RunState) -> bool:
        """把下一条插话并进上下文。消息本身已经落库。"""
        if s.inbox is None:
            return False
        async with s.inbox.lock:
            item = s.inbox.drain_one()
        if item is None:
            return False
        await self._append_message(
            s,
            role="user",
            content=item["content"],
            attachments=item.get("attachments"),
            skill_names=item.get("skill_names"),
        )
        return True

    async def _process_pending_tool_calls(
        self, s: _RunState, confirmation: Confirmation | None
    ) -> None:
        last_assistant = next((m for m in reversed(s.history) if m.role == "assistant"), None)
        if last_assistant is None or not last_assistant.tool_calls:
            return
        resolved = {m.tool_call_id for m in s.history if m.role == "tool"}
        pending = [tc for tc in last_assistant.tool_calls if tc["id"] not in resolved]
        ready: list[_ReadyTool] = []
        for tc in pending:
            if s.inbox is not None and s.inbox.pending():
                await self._skip_tool(s, tc)
                continue
            prepared = await self._prepare_tool_call(s, tc, confirmation)
            if prepared is _PAUSE:
                await self._run_ready_tools(s, ready)
                raise _Paused
            if isinstance(prepared, _ReadyTool):
                ready.append(prepared)
        await self._run_ready_tools(s, ready)

    async def _prepare_tool_call(
        self, s: _RunState, tc: dict[str, str], confirmation: Confirmation | None
    ) -> "_ReadyTool | None | _PauseMark":
        call_id, name, raw_args = tc["id"], tc["name"], tc["arguments"]
        attrs = {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": name,
            "gen_ai.tool.call.id": call_id,
        }

        tool = self.registry.get(name)
        if tool is None:
            await self._tool_failure(
                s, tc, attrs, raw_args, "unknown_tool", f"不存在名为 {name} 的工具"
            )
            return

        try:
            parsed = json.loads(raw_args or "{}")
            args = tool.Args.model_validate(parsed)
        except json.JSONDecodeError as e:
            await self._tool_failure(
                s, tc, attrs, raw_args, "invalid_json", f"参数不是合法 JSON：{e}"
            )
            return
        except ValidationError as e:
            details = e.errors(include_url=False, include_context=False)
            await self._tool_failure(
                s, tc, attrs, parsed, "invalid_arguments", "参数校验失败", details=details
            )
            return

        decision = s.guard.before_tool_call(tool, args, s.ctx)
        if decision.action == "block":
            step = await s.recorder.start(
                "guardrail",
                "tool_blocked",
                input={"tool_call_id": call_id, "tool_name": name},
                attributes=attrs,
            )
            await s.recorder.end(step, "blocked", output={"reason": decision.reason})
            await self._append_tool_result(s, tc, {"error": "blocked", "message": decision.reason})
            return

        permit_outside = decision.outside and decision.action == "allow"
        if decision.action == "confirm":
            matched = (
                confirmation if confirmation and confirmation.tool_call_id == call_id else None
            )
            if matched is None:
                await self._request_confirmation(
                    s, tc, args.model_dump(), decision.reason, attrs, decision.action_class
                )
                return _PAUSE
            await self._resolve_confirmation(s, call_id, matched.approved, matched.choice)
            if not matched.approved:
                await self._append_tool_result(
                    s, tc, {"error": "rejected_by_user", "message": "用户拒绝执行该操作"}
                )
                return None
            if matched.choice == "session" and decision.action_class:
                await self._remember_grant(s, decision.action_class)
            permit_outside = decision.outside

        return _ReadyTool(
            tc=tc, tool=tool, args=args, attrs=attrs, permit_outside=permit_outside
        )

    async def _run_ready_tools(self, s: _RunState, ready: list[_ReadyTool]) -> None:
        if not ready:
            return

        async def invoke(item: _ReadyTool) -> tuple[str, Any]:
            token = allow_outside.set(item.permit_outside)
            try:
                output = await asyncio.wait_for(
                    item.tool.run(item.args, s.ctx), timeout=item.tool.timeout_s
                )
            except TimeoutError:
                message = f"工具执行超过 {item.tool.timeout_s:g} 秒未完成，已中止"
                return "timeout", message
            except ToolError as e:
                return "tool_error", str(e)
            except Exception as e:  # noqa: BLE001  # 工具内部的意外错误也回填给模型，不中断运行
                return "internal_error", f"{type(e).__name__}: {e}"
            finally:
                allow_outside.reset(token)
            return "ok", output

        outcomes = await asyncio.gather(*(invoke(item) for item in ready))
        for item, (status, payload) in zip(ready, outcomes, strict=True):
            step = await s.recorder.start(
                "tool_call", item.tool.name, input=item.args.model_dump(), attributes=item.attrs
            )
            if status == "ok":
                await s.recorder.end(step, "ok", output=payload)
                await self._append_tool_result(s, item.tc, payload)
                s.consecutive_failures = 0
                continue
            if status == "timeout":
                await s.recorder.end(step, "timeout", error=payload)
                await self._append_tool_result(
                    s, item.tc, {"error": "timeout", "message": payload}
                )
            elif status == "tool_error":
                await s.recorder.end(step, "error", error=payload)
                await self._append_tool_result(
                    s, item.tc, {"error": "tool_error", "message": payload}
                )
            else:
                await s.recorder.end(step, "error", error=payload)
                await self._append_tool_result(
                    s, item.tc, {"error": "internal_error", "message": "工具内部错误"}
                )
            s.consecutive_failures += 1

    async def _skip_tool(self, s: _RunState, tc: dict[str, str]) -> None:
        await self._append_tool_result(
            s, tc, {"error": "skipped", "message": "用户插话，这个工具还没执行"}
        )

    async def _tool_failure(
        self,
        s: _RunState,
        tc: dict[str, str],
        attrs: dict[str, Any],
        input: Any,
        code: str,
        message: str,
        details: Any = None,
    ) -> None:
        step = await s.recorder.start("tool_call", tc["name"], input=input, attributes=attrs)
        payload: dict[str, Any] = {"error": code, "message": message}
        if details is not None:
            payload["details"] = details
        await s.recorder.end(step, "error", output=payload, error=message)
        await self._append_tool_result(s, tc, payload)
        s.consecutive_failures += 1

    async def _request_confirmation(
        self,
        s: _RunState,
        tc: dict[str, str],
        args: dict[str, Any],
        reason: str,
        attrs: dict[str, Any],
        action_class: str = "",
    ) -> None:
        payload = {
            "run_id": str(s.run.id),
            "tool_call_id": tc["id"],
            "tool_name": tc["name"],
            "arguments": args,
            "reason": reason,
            "action": action_class,
        }
        step = await s.recorder.start(
            "guardrail", "confirmation_required", input=payload, attributes=attrs, status="pending"
        )
        await s.emit("confirmation.required", {**payload, "step_id": str(step.id)})

    async def _remember_grant(self, s: _RunState, action_class: str) -> None:
        chat = await s.db.get(ChatSession, s.run.session_id)
        if chat is None:
            return
        grants = list(chat.permission_grants or [])
        if action_class not in grants:
            grants.append(action_class)
            chat.permission_grants = grants
            await s.db.commit()
        s.guard.grants.add(action_class)

    async def _resolve_confirmation(
        self, s: _RunState, call_id: str, approved: bool, choice: str
    ) -> None:
        steps = await s.db.scalars(
            select(Step).where(
                Step.run_id == s.run.id,
                Step.type == "guardrail",
                Step.name == "confirmation_required",
                Step.status == "pending",
            )
        )
        for step in steps:
            if step.input and step.input.get("tool_call_id") == call_id:
                await s.recorder.end(
                    step,
                    "approved" if approved else "rejected",
                    output={"approved": approved, "choice": choice},
                )

    async def _guardrail_stop(self, s: _RunState, name: str, reason: str) -> None:
        step = await s.recorder.start("guardrail", name, input={"reason": reason})
        await s.recorder.end(step, "blocked", output={"reason": reason})

    async def _close_open_step(self, s: _RunState, status: str, error: str) -> None:
        step = s.recorder.open_step
        if step is None:
            return
        await s.recorder.end(step, status, error=error)
        if step.type == "llm_call" and (s.partial_text or s.partial_reasoning):
            await self._append_message(
                s,
                role="assistant",
                content="".join(s.partial_text),
                reasoning="".join(s.partial_reasoning) or None,
            )
            s.partial_text = []
            s.partial_reasoning = []

    async def _append_tool_result(
        self, s: _RunState, tc: dict[str, str], result: dict[str, Any]
    ) -> None:
        await self._append_message(
            s, role="tool", content=_json(result), tool_call_id=tc["id"], tool_name=tc["name"]
        )

    async def _append_message(
        self,
        s: _RunState,
        *,
        role: str,
        content: str,
        tool_calls: list[dict[str, str]] | None = None,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        reasoning: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
        skill_names: list[str] | None = None,
    ) -> Message:
        if s.inbox is not None:
            async with s.inbox.lock:
                return await self._write_message(
                    s,
                    role=role,
                    content=content,
                    tool_calls=tool_calls,
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    reasoning=reasoning,
                    attachments=attachments,
                    skill_names=skill_names,
                )
        return await self._write_message(
            s,
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            reasoning=reasoning,
            attachments=attachments,
            skill_names=skill_names,
        )

    async def _write_message(
        self,
        s: _RunState,
        *,
        role: str,
        content: str,
        tool_calls: list[dict[str, str]] | None = None,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        reasoning: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
        skill_names: list[str] | None = None,
    ) -> Message:
        seq = (
            await s.db.scalar(
                select(func.max(Message.seq)).where(Message.session_id == s.run.session_id)
            )
            or 0
        ) + 1
        msg = Message(
            session_id=s.run.session_id,
            run_id=s.run.id,
            seq=seq,
            role=role,
            content=content,
            reasoning=reasoning,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            attachments=attachments,
            skill_names=skill_names,
        )
        s.db.add(msg)
        await s.db.commit()
        s.history.append(msg)
        await s.emit("message.completed", serialize_message(msg))
        return msg
