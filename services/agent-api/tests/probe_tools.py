"""仅供自动化测试的执行探针，不注册到用户工具列表。"""

import asyncio
import random
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from agent_api.tools.base import Tool, ToolContext, ToolError
from agent_api.tools.probes import Calculator, GetCurrentTime


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
    GetCurrentTime(), Calculator(), SlowTask(), FlakyTask(), SendNotification()
]
