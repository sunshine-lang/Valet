"""工具调用的权限。规则在代码里，不由模型决定要不要问用户。"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from agent_api.tools.base import Tool
from agent_api.workspace import Workspace, WorkspaceError

ActionClass = Literal["read", "write", "network", "command"]
VerdictKind = Literal["allow", "confirm", "block"]

FILE_READ = frozenset({"ls", "read_file"})
FILE_WRITE = frozenset({"write_file", "str_replace"})


@dataclass(frozen=True)
class Verdict:
    kind: VerdictKind
    action_class: str = ""
    reason: str = ""
    outside: bool = False


ALLOW = Verdict("allow")


def classify(
    tool: Tool, args: BaseModel, workspace: Workspace | None, mode: str = "assist"
) -> Verdict:
    permission = getattr(tool, "permission", None)
    if permission == "network":
        if mode == "ask":
            return Verdict("confirm", "network", "联网需要你授权")
        return ALLOW
    if permission == "command":
        if mode == "full":
            return ALLOW
        return Verdict("confirm", "command", "运行命令需要你授权")
    if tool.name not in FILE_READ and tool.name not in FILE_WRITE:
        return ALLOW
    if workspace is None:
        return Verdict("block", reason="当前没有项目目录")

    raw = "/" if tool.name == "ls" else str(getattr(args, "path", "") or "/")
    try:
        located = workspace.locate(raw)
    except WorkspaceError as error:
        return Verdict("block", reason=str(error))
    if located.denied:
        return Verdict("block", reason=located.denied)
    action: ActionClass = "write" if tool.name in FILE_WRITE else "read"
    if located.alias == "uploads" and action == "write":
        return Verdict("block", reason="上传目录只读")
    if located.outside:
        if mode == "full":
            return Verdict("allow", action, outside=True)
        verb = "修改" if action == "write" else "读取"
        return Verdict(
            "confirm",
            action,
            f"路径在项目目录之外，{verb}前需要你授权",
            outside=True,
        )
    return ALLOW
