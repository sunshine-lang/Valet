import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
from probe_tools import PROBE_TOOLS

from agent_api.config import Settings
from agent_api.llm import LLMRequest, LLMResult, TextDelta, ToolCall
from agent_api.main import create_app
from agent_api.tools import ToolRegistry, default_registry

Reply = LLMResult | Callable[[LLMRequest], LLMResult]


class FakeLLM:
    """按顺序返回预设回复的假模型；每次调用的请求会被记下来供断言。"""

    provider = "fake"
    priced = True

    def __init__(self) -> None:
        self.replies: list[Reply] = []
        self.requests: list[LLMRequest] = []
        self.delay_s = 0.0
        self.pause_s = 0.0
        self.pause_after_chars = 0

    def script(self, *replies: Reply) -> None:
        self.replies.extend(replies)

    async def stream(self, request: LLMRequest) -> AsyncIterator[TextDelta | LLMResult]:
        self.requests.append(request)
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        reply = self.replies.pop(0) if self.replies else text("（没有更多预设回复）")
        result = reply(request) if callable(reply) else reply
        sent = 0
        if self.pause_s and not result.content:
            await asyncio.sleep(self.pause_s)
        for ch in result.content:
            if self.pause_s and sent == self.pause_after_chars:
                await asyncio.sleep(self.pause_s)
            yield TextDelta(ch)
            sent += 1
        yield result


def text(content: str) -> LLMResult:
    return LLMResult(content=content, finish_reason="stop", input_tokens=100, output_tokens=20)


def call(name: str, args: dict[str, Any] | str, call_id: str = "call_1") -> LLMResult:
    raw = args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)
    return LLMResult(
        tool_calls=[ToolCall(id=call_id, name=name, arguments=raw)],
        finish_reason="tool_calls",
        input_tokens=100,
        output_tokens=10,
    )


async def _enable_example_tools(app) -> None:
    """示例工具默认关闭。循环测试仍要走探针路径，所以测试库里把它们打开。"""
    from agent_api.agent.settings import AgentSettings
    from agent_api.models import AgentConfig

    async with app.state.db.sessionmaker() as session:
        data = AgentSettings().model_dump()
        enabled = list(data["enabled_tools"])
        for tool in PROBE_TOOLS:
            if tool.name not in enabled:
                enabled.append(tool.name)
        data["enabled_tools"] = enabled
        session.add(AgentConfig(id=1, data=data))
        await session.commit()


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
async def client(tmp_path, fake_llm) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        dashscope_api_key="test",
        upload_dir=str(tmp_path / "workspaces"),
        user_skills_dir=str(tmp_path / "user-skills"),
    )
    registry = ToolRegistry([*default_registry().all(), *PROBE_TOOLS])
    app = create_app(settings=settings, llm=fake_llm, registry=registry)
    async with app.router.lifespan_context(app):
        await _enable_example_tools(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


def parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for block in body.split("\n\n"):
        lines = [line for line in block.splitlines() if line and not line.startswith(":")]
        if not lines:
            continue
        event = next(line[7:] for line in lines if line.startswith("event: "))
        data = next(line[6:] for line in lines if line.startswith("data: "))
        events.append((event, json.loads(data)))
    return events


async def send(client: httpx.AsyncClient, session_id: str, content: str):
    resp = await client.post(f"/api/sessions/{session_id}/messages", json={"content": content})
    assert resp.status_code == 200, resp.text
    return parse_sse(resp.text)


async def new_session(client: httpx.AsyncClient) -> str:
    resp = await client.post("/api/sessions")
    return resp.json()["id"]


def finished_run(events) -> dict[str, Any]:
    return next(data for name, data in events if name == "run.finished")


async def run_steps(client: httpx.AsyncClient, run_id: str) -> list[dict[str, Any]]:
    resp = await client.get(f"/api/runs/{run_id}")
    return resp.json()["steps"]
