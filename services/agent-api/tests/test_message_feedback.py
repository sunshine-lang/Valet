import uuid

import pytest
from conftest import call, new_session, send, text
from sqlalchemy import text as sql_text

from agent_api.agent.context import to_llm_messages
from agent_api.db import Database
from agent_api.models import ChatSession, Message


@pytest.fixture
async def answered_session(client, fake_llm):
    session_id = await new_session(client)
    fake_llm.script(text("这是 **AI 回复**。"))
    await send(client, session_id, "这是用户消息。")
    detail = (await client.get(f"/api/sessions/{session_id}")).json()
    assistant = next(m for m in detail["messages"] if m["role"] == "assistant")
    return session_id, assistant["id"]


async def test_feedback_persists_and_like_dislike_clear_are_exclusive(client, answered_session):
    session_id, message_id = answered_session
    path = f"/api/messages/{message_id}/feedback"
    original = (await client.get(f"/api/sessions/{session_id}")).json()
    for payload in (
        {"rating": "like", "reasons": [], "comment": ""},
        {
            "rating": "dislike",
            "reasons": ["context_error", "code_error", "other"],
            "comment": "  缺少可运行的示例  ",
        },
        {"rating": "like", "reasons": [], "comment": ""},
        {"rating": None},
    ):
        response = await client.put(path, json=payload)
        assert response.status_code == 200
        expected = (
            {**payload, "comment": payload["comment"].strip()}
            if payload["rating"] is not None
            else None
        )
        assert response.json() == {"message_id": message_id, "feedback": expected}
        detail = (await client.get(f"/api/sessions/{session_id}")).json()
        assert len(detail["messages"]) == len(original["messages"])
        assert detail["runs"] == original["runs"]
        assistant = next(m for m in detail["messages"] if m["id"] == message_id)
        assert assistant["feedback"] == expected
        assert assistant["content"] == "这是 **AI 回复**。"
        assert detail["messages"][0]["feedback"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {"rating": "dislike"},
        {"rating": "dislike", "reasons": ["unknown"]},
        {"rating": "dislike", "reasons": ["code_error", "code_error"]},
        {"rating": "dislike", "reasons": ["code_error"], "comment": "缺少示例"},
        {"rating": "dislike", "reasons": ["other"], "comment": "字" * 201},
        {"rating": "like", "reasons": ["code_error"]},
        {"rating": None, "reasons": ["other"]},
        {"rating": "unknown"},
    ],
)
async def test_invalid_feedback_is_rejected_without_mutation(client, answered_session, payload):
    session_id, message_id = answered_session
    response = await client.put(f"/api/messages/{message_id}/feedback", json=payload)
    assert response.status_code == 422
    detail = (await client.get(f"/api/sessions/{session_id}")).json()
    assert next(m for m in detail["messages"] if m["id"] == message_id)["feedback"] is None


async def test_other_reason_allows_optional_comment_up_to_200_characters(client, answered_session):
    _, message_id = answered_session
    for comment in ("", "字" * 200):
        response = await client.put(
            f"/api/messages/{message_id}/feedback",
            json={"rating": "dislike", "reasons": ["other"], "comment": comment},
        )
        assert response.status_code == 200
        assert response.json()["feedback"]["comment"] == comment


async def test_feedback_only_accepts_assistant_messages_with_text(client, fake_llm):
    session_id = await new_session(client)
    fake_llm.script(call("calculator", {"expression": "2 + 2"}), text("4"))
    await send(client, session_id, "计算 2 + 2")
    detail = (await client.get(f"/api/sessions/{session_id}")).json()
    unsupported = [
        m for m in detail["messages"] if m["role"] != "assistant" or not m["content"]
    ]
    assert {m["role"] for m in unsupported} == {"user", "assistant", "tool"}
    for message in unsupported:
        response = await client.put(
            f"/api/messages/{message['id']}/feedback", json={"rating": "like"}
        )
        assert response.status_code == 422
    missing = await client.put(
        f"/api/messages/{uuid.uuid4()}/feedback", json={"rating": "like"}
    )
    assert missing.status_code == 404


async def test_existing_database_adds_feedback_without_losing_history(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'legacy.db'}"
    db = Database(url)
    await db.create_all()
    async with db.sessionmaker() as session:
        conversation = ChatSession()
        session.add(conversation)
        await session.flush()
        message = Message(session_id=conversation.id, seq=1, role="assistant", content="旧回复")
        session.add(message)
        await session.commit()
        message_id = message.id
    async with db.engine.begin() as connection:
        await connection.execute(sql_text("ALTER TABLE messages DROP COLUMN feedback"))
    await db.dispose()

    upgraded = Database(url)
    await upgraded.create_all()
    await upgraded.create_all()
    async with upgraded.sessionmaker() as session:
        message = await session.get(Message, message_id)
        assert message.content == "旧回复"
        assert message.feedback is None
        message.feedback = {"rating": "like", "reasons": [], "comment": ""}
        await session.commit()
    await upgraded.dispose()

    reopened = Database(url)
    async with reopened.sessionmaker() as session:
        message = await session.get(Message, message_id)
        assert message.feedback["rating"] == "like"
    await reopened.dispose()


def test_feedback_is_not_sent_to_the_model():
    history = [
        Message(
            role="assistant", content="回复正文",
            feedback={"rating": "dislike", "reasons": ["other"], "comment": "仅用于反馈"},
        )
    ]
    assert to_llm_messages("系统提示", history)[1] == {"role": "assistant", "content": "回复正文"}
