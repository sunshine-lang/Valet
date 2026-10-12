import json

from agent_api.llm import LLMRequest, LLMResult
from agent_api.llm.mock import MockLLMClient
from agent_api.tools import default_registry

TOOLS = default_registry().schemas(default_registry().names())


async def _final(messages) -> LLMResult:
    client = MockLLMClient(char_delay_s=0)
    request = LLMRequest(
        model="deepseek-v4-flash-0731", messages=messages, tools=TOOLS, temperature=0
    )
    events = [e async for e in client.stream(request)]
    return events[-1]


async def test_mock_plans_tool_calls_from_keywords():
    result = await _final([{"role": "user", "content": "帮我算一下 (17 + 25) * 3"}])
    assert [tc.name for tc in result.tool_calls] == ["calculator"]
    assert json.loads(result.tool_calls[0].arguments)["expression"] == "(17 + 25) * 3"


async def test_mock_summarizes_tool_results():
    messages = [
        {"role": "user", "content": "几点了"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "get_current_time", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "c1",
            "content": json.dumps({"iso": "2026-10-09T16:00:00"}),
        },
    ]
    result = await _final(messages)
    assert not result.tool_calls
    assert "get_current_time" in result.content
