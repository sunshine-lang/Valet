from typing import Protocol

from agent_api.models import Run, Step


class TraceExporter(Protocol):
    """把运行和步骤导出到外部可观测平台（OpenTelemetry、Langfuse 云、Phoenix 等）。

    Step.attributes 已按 OpenTelemetry GenAI 语义约定命名，导出器只需映射成 span。
    """

    async def on_step_end(self, run: Run, step: Step) -> None: ...

    async def on_run_end(self, run: Run) -> None: ...


class NoopExporter:
    async def on_step_end(self, run: Run, step: Step) -> None:
        return None

    async def on_run_end(self, run: Run) -> None:
        return None
