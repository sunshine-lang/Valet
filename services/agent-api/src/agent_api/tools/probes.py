"""探针工具：没有业务含义，每个工具专门触发主循环里的一条执行路径。"""

import ast
import asyncio
import operator
import random
import uuid
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field

from agent_api.tools.base import Tool, ToolContext, ToolError


class GetCurrentTime(Tool):
    name = "get_current_time"
    description = "获取指定时区的当前日期和时间。"
    example = True
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
    example = True
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


class SlowTask(Tool):
    name = "slow_task"
    description = "执行一个耗时指定秒数的模拟任务。该工具的超时上限是 10 秒。"
    example = True
    probes = "超时与取消"
    timeout_s = 10.0

    class Args(BaseModel):
        seconds: float = Field(..., ge=0, le=60, description="任务耗时（秒），0 到 60")
        label: str = Field("模拟任务", max_length=50, description="任务名称")

    async def run(self, args: Args, ctx: ToolContext) -> dict[str, Any]:
        await asyncio.sleep(args.seconds)
        return {"label": args.label, "elapsed_seconds": args.seconds, "done": True}


class FlakyTask(Tool):
    name = "flaky_task"
    description = "执行一个可能随机失败的模拟任务，用于测试错误处理。"
    example = True
    probes = "报错回填与连续失败停止"

    class Args(BaseModel):
        failure_rate: float = Field(0.5, ge=0, le=1, description="失败概率，0 到 1")
        mode: Literal["auto", "fail", "succeed"] = Field(
            "auto", description="auto 按概率；fail 必定失败；succeed 必定成功"
        )

    async def run(self, args: Args, ctx: ToolContext) -> dict[str, Any]:
        roll = random.random()
        failed = args.mode == "fail" or (args.mode == "auto" and roll < args.failure_rate)
        if failed:
            raise ToolError(f"模拟故障：下游服务返回 503（随机数 {roll:.2f}）")
        return {"ok": True, "roll": round(roll, 2)}


class SendNotification(Tool):
    name = "send_notification"
    description = "向指定接收人发送一条通知（模拟，不会真的发出）。执行前需要用户确认。"
    example = True
    probes = "需确认后执行"
    requires_confirmation = True

    class Args(BaseModel):
        recipient: str = Field(..., min_length=1, max_length=64, description="接收人")
        message: str = Field(..., min_length=1, max_length=500, description="通知内容")
        channel: Literal["im", "email", "sms"] = Field("im", description="发送渠道")

    async def run(self, args: Args, ctx: ToolContext) -> dict[str, Any]:
        return {
            "delivered": True,
            "simulated": True,
            "notification_id": f"ntf_{uuid.uuid4().hex[:10]}",
            "recipient": args.recipient,
            "channel": args.channel,
        }


PROBE_TOOLS: list[Tool] = [
    GetCurrentTime(),
    Calculator(),
    SlowTask(),
    FlakyTask(),
    SendNotification(),
]
