import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel


class ToolError(Exception):
    """工具执行中的可预期错误：错误信息会原样回填给模型，让它决定如何修正。"""


@dataclass(frozen=True)
class ToolContext:
    """由执行层注入的上下文。模型无法通过工具参数伪造这里的任何字段。"""

    session_id: uuid.UUID
    run_id: uuid.UUID
    workspace: Any = None
    skills_dir: Path | None = None
    user_skills_dir: Path | None = None
    installed_skills: list[str] | None = None


class Tool:
    name: ClassVar[str]
    description: ClassVar[str]
    Args: ClassVar[type[BaseModel]]
    requires_confirmation: ClassVar[bool] = False
    # network / command 默认要授权。文件类由路径另判。
    permission: ClassVar[str | None] = None
    timeout_s: ClassVar[float] = 10.0
    # 示例工具用来试主循环，注册进列表，但新项目默认不打开。
    example: ClassVar[bool] = False
    # 给前端看的分类标签，便于在工具列表里说明这个工具在测哪条路径
    probes: ClassVar[str] = ""

    async def run(self, args: BaseModel, ctx: ToolContext) -> dict[str, Any]:
        raise NotImplementedError

    @classmethod
    def schema(cls) -> dict[str, Any]:
        params = cls.Args.model_json_schema()
        params.pop("title", None)
        for prop in params.get("properties", {}).values():
            prop.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": cls.description,
                "parameters": params,
            },
        }


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {t.name: t for t in tools}

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return list(self._tools)

    def schemas(self, enabled: list[str]) -> list[dict[str, Any]]:
        return [t.schema() for name, t in self._tools.items() if name in enabled]
