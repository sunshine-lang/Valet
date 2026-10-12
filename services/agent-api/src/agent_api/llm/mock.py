"""本地模拟模型：不调外部接口、不计费，按关键词触发探针工具，用于无 Key 演示和前端开发。"""

import asyncio
import json
import re
import uuid
from collections.abc import AsyncIterator
from typing import Any

from agent_api.llm.base import LLMRequest, LLMResult, TextDelta, ToolCall


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 2)


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        if any(isinstance(part, dict) and part.get("type") == "image_url" for part in content):
            parts.append("（附带图片）")
        return "\n".join(parts)
    return str(content or "")


def _plan(text: str, tools: set[str]) -> list[tuple[str, dict[str, Any]]]:
    calls: list[tuple[str, dict[str, Any]]] = []
    if "get_current_time" in tools and re.search(r"几点|时间|日期", text):
        calls.append(("get_current_time", {"timezone": "Asia/Shanghai"}))
        if "纽约" in text:
            calls.append(("get_current_time", {"timezone": "America/New_York"}))
    if "calculator" in tools and re.search(r"算", text):
        expr = re.sub(r"[^\d+\-*/().\s÷×]", "", text).replace("÷", "/").replace("×", "*").strip()
        calls.append(("calculator", {"expression": expr or "1+1"}))
    if "slow_task" in tools and re.search(r"慢任务|slow", text):
        m = re.search(r"(\d+(?:\.\d+)?)\s*秒", text)
        calls.append(("slow_task", {"seconds": float(m.group(1)) if m else 3}))
    if "flaky_task" in tools and re.search(r"失败|flaky", text):
        calls.append(("flaky_task", {"mode": "fail" if "fail" in text else "auto"}))
    if "send_notification" in tools and "通知" in text:
        m = re.search(r"给(.{1,8}?)发", text)
        body = text.split("：", 1)[1] if "：" in text else text
        calls.append(
            ("send_notification", {"recipient": m.group(1) if m else "张三", "message": body})
        )
    return calls


def _summarize(results: list[dict[str, Any]]) -> str:
    lines = []
    for r in results:
        data = r["data"]
        if isinstance(data, dict) and "error" in data:
            lines.append(f"- `{r['name']}` 没成功：{data.get('message', data['error'])}")
        else:
            lines.append(f"- `{r['name']}` 返回：{json.dumps(data, ensure_ascii=False)}")
    return "（模拟模型）工具结果如下：\n" + "\n".join(lines)


class MockLLMClient:
    provider = "mock"
    priced = False

    def __init__(self, char_delay_s: float = 0.012) -> None:
        self._delay = char_delay_s

    async def stream(self, request: LLMRequest) -> AsyncIterator[TextDelta | LLMResult]:
        messages = request.messages
        prompt_tokens = sum(_approx_tokens(_message_text(m.get("content"))) for m in messages)
        tools = {t["function"]["name"] for t in request.tools}

        content = ""
        tool_calls: list[ToolCall] = []
        if messages[-1]["role"] == "tool":
            results = []
            for m in reversed(messages):
                if m["role"] != "tool":
                    break
                name = next(
                    (
                        tc["function"]["name"]
                        for a in messages
                        if a["role"] == "assistant"
                        for tc in a.get("tool_calls", [])
                        if tc["id"] == m["tool_call_id"]
                    ),
                    "tool",
                )
                try:
                    data = json.loads(m["content"])
                except json.JSONDecodeError:
                    data = m["content"]
                results.insert(0, {"name": name, "data": data})
            content = _summarize(results)
        else:
            user = _message_text(
                next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
            )
            plan = _plan(user, tools) if tools else []
            if plan:
                tool_calls = [
                    ToolCall(
                        f"call_{uuid.uuid4().hex[:8]}", name, json.dumps(args, ensure_ascii=False)
                    )
                    for name, args in plan
                ]
            else:
                content = (
                    f"（模拟模型）收到：{user}。"
                    "配置 DASHSCOPE_API_KEY 并把 LLM_PROVIDER 改回 dashscope 即可使用真实模型。"
                )

        for ch in content:
            await asyncio.sleep(self._delay)
            yield TextDelta(ch)
        await asyncio.sleep(0.2 if tool_calls else 0)
        yield LLMResult(
            content=content,
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else "stop",
            input_tokens=prompt_tokens,
            output_tokens=_approx_tokens(content) + 10 * len(tool_calls),
            response_model="mock",
        )
