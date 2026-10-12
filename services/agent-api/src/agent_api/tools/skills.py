"""读取已安装技能的说明，以及把新技能写到用户技能目录。"""

from typing import Any

from pydantic import BaseModel, Field

from agent_api.skills import find_in_catalog
from agent_api.skills.catalog import _NAME, _load_one
from agent_api.tools.base import Tool, ToolContext, ToolError


class ReadSkill(Tool):
    name = "read_skill"
    description = (
        "读取一个已安装技能的说明全文。系统提示里只有技能名字和何时使用。"
        "确认与当前任务相关后再调用，然后按说明做。"
    )
    probes = "技能"

    class Args(BaseModel):
        name: str = Field(
            ..., min_length=1, max_length=64, description="技能名字，例如 read-uploads"
        )

    async def run(self, args: Args, ctx: ToolContext) -> dict[str, Any]:
        skill = find_in_catalog(ctx.skills_dir, ctx.user_skills_dir, args.name)
        if skill is None:
            raise ToolError(f"没有名为 {args.name} 的技能")
        if ctx.installed_skills is not None and args.name not in ctx.installed_skills:
            raise ToolError(f"技能 {args.name} 还没有安装")
        return {"name": skill.name, "title": skill.title, "instructions": skill.body}


class CreateSkill(Tool):
    name = "create_skill"
    description = (
        "创建或更新一份用户技能，写入用户技能目录。用户要新建技能或把工作流保存成技能时使用。"
        "不能改内置技能文件。"
    )
    probes = "技能"

    class Args(BaseModel):
        name: str = Field(
            ..., min_length=1, max_length=64, description="技能名字，小写字母、数字和连字符"
        )
        description: str = Field(
            ..., min_length=1, max_length=1024, description="做什么，以及什么时候使用"
        )
        body: str = Field(
            ..., min_length=1, max_length=100_000, description="不含 YAML 头的 Markdown 正文"
        )
        title: str = Field("", max_length=40, description="给人看的标题，可空")

    async def run(self, args: Args, ctx: ToolContext) -> dict[str, Any]:
        if ctx.user_skills_dir is None:
            raise ToolError("没有配置用户技能目录")
        if not _NAME.fullmatch(args.name):
            raise ToolError("技能名只能使用小写字母、数字和连字符，且不能以连字符开头或结尾")
        root = ctx.user_skills_dir
        directory = root / args.name
        directory.mkdir(parents=True, exist_ok=True)
        title = args.title.strip()
        front = ["---", f"name: {args.name}", f"description: {args.description.strip()}"]
        if title:
            front.extend(["metadata:", f"  title: {title}"])
        front.append("---")
        document = directory / "SKILL.md"
        document.write_text("\n".join(front) + "\n\n" + args.body.strip() + "\n", encoding="utf-8")
        skill = _load_one(directory, "user")
        if skill is None:
            document.unlink(missing_ok=True)
            raise ToolError("技能内容无法通过校验，没有保存")
        return {
            "name": skill.name,
            "title": skill.title,
            "path": f"data/skills/{skill.name}/SKILL.md",
            "message": "已写入用户技能目录。刷新技能页即可看到。",
        }


SKILL_TOOLS: list[Tool] = [ReadSkill(), CreateSkill()]
