"""会话目录里的文件工具。路径只能是 /uploads、/workspace、/outputs。"""

from typing import Any

from pydantic import BaseModel, Field

from agent_api.tools.base import Tool, ToolContext, ToolError
from agent_api.workspace import Workspace, WorkspaceError

FILE_GUIDE = """
文件工具的工作区是项目根目录。路径用相对路径，例如 README.md、web/src/App.vue。
- /uploads：当前会话上传的文件，只读。
- /outputs：要交给用户的结果，可写。
也可以直接读写项目里的其他文件。不要读写 .env、密钥和 .git。
修改已有文件之前必须先 read_file。项目目录之外的路径需要用户授权。"""


def _workspace(ctx: ToolContext) -> Workspace:
    workspace = ctx.workspace
    if not isinstance(workspace, Workspace):
        raise ToolError("当前会话没有工作区")
    return workspace


def _run(workspace: Workspace, action) -> dict[str, Any]:
    try:
        return action(workspace)
    except WorkspaceError as e:
        raise ToolError(str(e)) from e


class ListFiles(Tool):
    name = "ls"
    description = "列出项目目录。path 可以是项目相对路径，或 /uploads、/outputs。"
    probes = "文件"

    class Args(BaseModel):
        path: str = Field("/", description="要列出的目录，例如 /uploads")

    async def run(self, args: Args, ctx: ToolContext) -> dict[str, Any]:
        def action(ws: Workspace) -> dict[str, Any]:
            path = args.path or "/"
            return {"path": path, "entries": ws.list_dir(path)}

        return _run(_workspace(ctx), action)


class ReadFile(Tool):
    name = "read_file"
    description = "读取会话目录中的文本文件。单次最多返回 10 万字节。二进制文件会拒绝。"
    probes = "文件"

    class Args(BaseModel):
        path: str = Field(..., description="项目内的相对路径，或 /uploads、/outputs 下的文件")

    async def run(self, args: Args, ctx: ToolContext) -> dict[str, Any]:
        return _run(_workspace(ctx), lambda ws: ws.read_text(args.path))


class WriteFile(Tool):
    name = "write_file"
    description = (
        "把文本写入项目目录或 /outputs。不能写 /uploads、.env、密钥和 .git。"
        "覆盖已有文件前必须先 read_file。"
    )
    probes = "文件"

    class Args(BaseModel):
        path: str = Field(..., description="文件路径，例如 /outputs/reply.md")
        content: str = Field(..., max_length=100_000, description="完整的文件内容")

    async def run(self, args: Args, ctx: ToolContext) -> dict[str, Any]:
        return _run(_workspace(ctx), lambda ws: ws.write_text(args.path, args.content))


class ReplaceInFile(Tool):
    name = "str_replace"
    description = (
        "替换项目里已读过的文件中的一段原文。原文必须只出现一次。不能改 .env、密钥和 .git。"
    )
    probes = "文件"

    class Args(BaseModel):
        path: str = Field(..., description="文件路径")
        old_string: str = Field(..., description="要被替换的原文，必须唯一")
        new_string: str = Field(..., description="替换后的文本")

    async def run(self, args: Args, ctx: ToolContext) -> dict[str, Any]:
        return _run(
            _workspace(ctx),
            lambda ws: ws.replace_text(args.path, args.old_string, args.new_string),
        )


FILE_TOOLS: list[Tool] = [ListFiles(), ReadFile(), WriteFile(), ReplaceInFile()]
FILE_TOOL_NAMES = tuple(tool.name for tool in FILE_TOOLS)
