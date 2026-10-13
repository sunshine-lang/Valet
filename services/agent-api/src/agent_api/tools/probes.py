"""执行真实计算与时间查询的实用工具。"""

import ast
import operator
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field

from agent_api.tools.base import Tool, ToolContext, ToolError


class GetCurrentTime(Tool):
    name = "get_current_time"
    description = "获取指定时区的当前日期和时间。"
    probes = "成功路径"

    class Args(BaseModel):
        timezone: str = Field("Asia/Shanghai", description="IANA 时区名，例如 Asia/Shanghai")

    async def run(self, args: Args, ctx: ToolContext) -> dict[str, Any]:
        try:
            tz = ZoneInfo(args.timezone)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ToolError(f"未知时区：{args.timezone}，请使用 IANA 时区名") from e
        now = datetime.now(tz)
        return {
            "timezone": args.timezone,
            "iso": now.isoformat(timespec="seconds"),
            "weekday": "一二三四五六日"[now.weekday()],
        }


_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ToolError("指数过大（上限 100）")
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand))
    raise ToolError("只支持数字、括号和 + - * / // % ** 运算符")


class Calculator(Tool):
    name = "calculator"
    description = "计算算术表达式。只支持数字、括号和 + - * / // % ** 运算符。"
    probes = "参数校验与自我修正"

    class Args(BaseModel):
        expression: str = Field(
            ..., min_length=1, max_length=200, description="算术表达式，例如 (3 + 4) * 2"
        )

    async def run(self, args: Args, ctx: ToolContext) -> dict[str, Any]:
        try:
            tree = ast.parse(args.expression, mode="eval")
        except SyntaxError as e:
            raise ToolError(f"表达式语法错误：{args.expression}") from e
        try:
            result = _eval_node(tree.body)
        except ZeroDivisionError as e:
            raise ToolError("除数不能为 0") from e
        return {"expression": args.expression, "result": result}


UTILITY_TOOLS: list[Tool] = [GetCurrentTime(), Calculator()]
