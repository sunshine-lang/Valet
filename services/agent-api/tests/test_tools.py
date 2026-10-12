import uuid

import pytest

from agent_api.agent.settings import AgentSettings
from agent_api.tools import ToolContext, ToolError
from agent_api.tools.live import WebSearch
from agent_api.tools.probes import Calculator, GetCurrentTime

CTX = ToolContext(session_id=uuid.uuid4(), run_id=uuid.uuid4())


def test_new_project_leaves_example_tools_off():
    enabled = set(AgentSettings().enabled_tools)
    assert "web_search" in enabled
    assert "read_file" in enabled
    assert "calculator" not in enabled


def test_web_search_uses_the_user_language_once():
    assert "搜一次" in WebSearch.description
    assert "另一种语言" in WebSearch.description


@pytest.mark.parametrize(
    ("expr", "expected"),
    [("1+2*3", 7), ("(3+4)*2", 14), ("2**10", 1024), ("-5 // 2", -3), ("7 % 3", 1)],
)
async def test_calculator(expr, expected):
    out = await Calculator().run(Calculator.Args(expression=expr), CTX)
    assert out["result"] == expected


@pytest.mark.parametrize("expr", ["__import__('os')", "a + 1", "2 ** 1000", "1/0", "1 +"])
async def test_calculator_rejects(expr):
    with pytest.raises(ToolError):
        await Calculator().run(Calculator.Args(expression=expr), CTX)


async def test_unknown_timezone():
    with pytest.raises(ToolError):
        await GetCurrentTime().run(GetCurrentTime.Args(timezone="Mars/Base"), CTX)


def test_schema_has_no_titles():
    schema = Calculator.schema()["function"]["parameters"]
    assert "title" not in schema
    assert "title" not in schema["properties"]["expression"]
