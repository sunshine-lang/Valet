"""护栏层：位于「模型决定调用工具」与「工具真正执行」之间，由代码而不是模型做决定。"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from agent_api.permissions import classify
from agent_api.tools.base import Tool, ToolContext
from agent_api.workspace import Workspace


@dataclass(frozen=True)
class Decision:
    action: Literal["allow", "confirm", "block"]
    reason: str = ""
    action_class: str = ""
    outside: bool = False


ALLOW = Decision("allow")


class Guardrails:
    def __init__(
        self,
        enabled_tools: list[str],
        grants: set[str] | None = None,
        mode: str = "assist",
    ) -> None:
        self._enabled = set(enabled_tools)
        self.grants = set(grants or ())
        self.mode = mode if mode in {"ask", "assist", "full"} else "assist"

    def before_tool_call(self, tool: Tool, args: BaseModel, ctx: ToolContext) -> Decision:
        if tool.name not in self._enabled:
            return Decision("block", f"工具 {tool.name} 未在当前配置中启用")
        if tool.requires_confirmation:
            return Decision("confirm", f"工具 {tool.name} 需要用户确认后才能执行")
        workspace = ctx.workspace if isinstance(ctx.workspace, Workspace) else None
        verdict = classify(tool, args, workspace, self.mode)
        if verdict.kind == "block":
            return Decision("block", verdict.reason)
        if verdict.kind == "confirm" and verdict.action_class not in self.grants:
            return Decision("confirm", verdict.reason, verdict.action_class, verdict.outside)
        if verdict.outside:
            return Decision("allow", action_class=verdict.action_class, outside=True)
        return ALLOW
