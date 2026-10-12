import uuid

from agent_api.agent.context import prune_history, to_llm_messages
from agent_api.llm import reasoning_params
from agent_api.models import Message


def test_reasoning_is_sent_back_with_tool_calls():
    session_id = uuid.uuid4()
    history = [
        Message(session_id=session_id, seq=1, role="user", content="现在北京天气怎么样"),
        Message(
            session_id=session_id,
            seq=2,
            role="assistant",
            content="",
            reasoning="需要调用天气工具",
            tool_calls=[{"id": "c1", "name": "get_weather", "arguments": "{}"}],
        ),
    ]
    messages = to_llm_messages("你是 Valet", history)
    assistant = messages[2]
    assert assistant["reasoning_content"] == "需要调用天气工具"
    assert messages[3]["role"] == "tool"


def test_prune_keeps_recent_messages_and_tool_pairs():
    session_id = uuid.uuid4()
    history = [
        Message(session_id=session_id, seq=1, role="user", content="旧" * 100),
        Message(
            session_id=session_id,
            seq=2,
            role="assistant",
            content="",
            tool_calls=[{"id": "c1", "name": "calculator", "arguments": "{}"}],
        ),
        Message(
            session_id=session_id,
            seq=3,
            role="tool",
            content="14",
            tool_call_id="c1",
            tool_name="calculator",
        ),
        Message(session_id=session_id, seq=4, role="user", content="新问题"),
    ]
    kept, omitted = prune_history(history, budget_chars=20)
    assert omitted is True
    assert [message.seq for message in kept] == [4]
    wide, not_omitted = prune_history(history, budget_chars=10_000)
    assert not_omitted is False
    assert [message.seq for message in wide] == [1, 2, 3, 4]
    paired, pair_omitted = prune_history(history, budget_chars=80)
    assert pair_omitted is True
    assert [message.seq for message in paired] == [2, 3, 4]


def test_reasoning_effort_maps_per_model_family():
    assert reasoning_params("deepseek-v4-flash-0731", "off") == {"enable_thinking": False}
    assert reasoning_params("deepseek-v4-flash-0731", "max")["reasoning_effort"] == "max"
    assert reasoning_params("qwen3.8-max-0902", "high")["reasoning_effort"] == "xhigh"
    assert reasoning_params("deepseek-v4.1-flash", "medium")["reasoning_effort"] == "high"
