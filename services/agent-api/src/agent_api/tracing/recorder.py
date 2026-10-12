from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.models import Run, Step, as_utc, utcnow
from agent_api.tracing.exporter import TraceExporter

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]


def iso_utc(dt: datetime | None) -> str | None:
    return as_utc(dt).isoformat() if dt else None


def _ms_between(start: datetime, end: datetime) -> int:
    return int((as_utc(end) - as_utc(start)).total_seconds() * 1000)


def serialize_step(step: Step) -> dict[str, Any]:
    return {
        "id": str(step.id),
        "run_id": str(step.run_id),
        "seq": step.seq,
        "type": step.type,
        "name": step.name,
        "status": step.status,
        "input": step.input,
        "output": step.output,
        "error": step.error,
        "attributes": step.attributes,
        "input_tokens": step.input_tokens,
        "output_tokens": step.output_tokens,
        "cost_cny": step.cost_cny,
        "started_at": iso_utc(step.started_at),
        "ended_at": iso_utc(step.ended_at),
        "duration_ms": step.duration_ms,
    }


def serialize_run(run: Run) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "session_id": str(run.session_id),
        "status": run.status,
        "stop_reason": run.stop_reason,
        "error": run.error,
        "input_text": run.input_text,
        "config_snapshot": {
            key: value for key, value in (run.config_snapshot or {}).items() if key != "api_key"
        },
        "llm_calls": run.llm_calls,
        "tool_calls": run.tool_calls,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "cost_cny": run.cost_cny,
        "started_at": iso_utc(run.started_at),
        "ended_at": iso_utc(run.ended_at),
        "duration_ms": run.duration_ms,
    }


class TraceRecorder:
    """把每一步写进数据库、累加到运行汇总，并实时推送给前端。"""

    def __init__(self, db: AsyncSession, run: Run, emit: Emit, exporter: TraceExporter) -> None:
        self.db = db
        self.run = run
        self.emit = emit
        self.exporter = exporter
        self._seq = 0
        self.open_step: Step | None = None

    def init_seq(self, last_seq: int) -> None:
        self._seq = last_seq

    async def start(
        self,
        type_: str,
        name: str,
        *,
        input: Any = None,
        attributes: dict[str, Any] | None = None,
        status: str = "running",
    ) -> Step:
        self._seq += 1
        step = Step(
            run_id=self.run.id,
            seq=self._seq,
            type=type_,
            name=name,
            status=status,
            input=input,
            attributes={"gen_ai.conversation.id": str(self.run.session_id), **(attributes or {})},
            started_at=utcnow(),
        )
        self.db.add(step)
        await self.db.commit()
        if status == "running":
            self.open_step = step
        await self.emit("step.started", serialize_step(step))
        return step

    async def end(
        self,
        step: Step,
        status: str,
        *,
        output: Any = None,
        error: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost_cny: float | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Step:
        step.status = status
        step.output = output
        step.error = error
        step.ended_at = utcnow()
        step.duration_ms = _ms_between(step.started_at, step.ended_at)
        if attributes:
            step.attributes = {**step.attributes, **attributes}
        if input_tokens is not None:
            step.input_tokens = input_tokens
            step.output_tokens = output_tokens
            step.cost_cny = cost_cny
            self.run.input_tokens += input_tokens
            self.run.output_tokens += output_tokens or 0
            self.run.cost_cny += cost_cny or 0.0
        if step.type == "llm_call":
            self.run.llm_calls += 1
        elif step.type == "tool_call":
            self.run.tool_calls += 1
        if self.open_step is step:
            self.open_step = None
        await self.db.commit()
        await self.emit("step.completed", serialize_step(step))
        await self.exporter.on_step_end(self.run, step)
        return step

    async def finish_run(
        self, status: str, *, stop_reason: str | None = None, error: str | None = None
    ) -> None:
        self.run.status = status
        self.run.stop_reason = stop_reason
        self.run.error = error
        if status != "awaiting_confirmation":
            self.run.ended_at = utcnow()
            self.run.duration_ms = _ms_between(self.run.started_at, self.run.ended_at)
        await self.db.commit()
        await self.emit("run.finished", serialize_run(self.run))
        await self.exporter.on_run_end(self.run)
