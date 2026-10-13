import json
from pathlib import Path
from typing import Any

from agent_api.models import Message
from agent_api.tracing.recorder import iso_utc
from agent_api.uploads import public_attachment, user_llm_content

INTERRUPTED_RESULT = json.dumps(
    {"error": "interrupted", "message": "该工具调用未执行完成（运行被取消或中断）"},
    ensure_ascii=False,
)
SKIPPED_RESULT = json.dumps(
    {"error": "skipped", "message": "用户插话，这个工具还没执行"},
    ensure_ascii=False,
)
# 粗略按字符预算保留最近的对话。中文大约 1 到 2 字一个 token。
CONTEXT_CHAR_BUDGET = 24_000
PRUNE_NOTE = "更早的对话已省略，下面只保留最近的内容。"


def serialize_message(m: Message) -> dict[str, Any]:
    return {
        "id": str(m.id),
        "session_id": str(m.session_id),
        "run_id": str(m.run_id) if m.run_id else None,
        "seq": m.seq,
        "role": m.role,
        "content": m.content,
        "reasoning": m.reasoning,
        "tool_calls": m.tool_calls,
        "tool_call_id": m.tool_call_id,
        "tool_name": m.tool_name,
        "attachments": (
            [public_attachment(item, str(m.session_id)) for item in m.attachments]
            if m.attachments
            else None
        ),
        "skill_names": m.skill_names,
        "feedback": m.feedback,
        "created_at": iso_utc(m.created_at),
    }


def _message_size(message: Message) -> int:
    size = len(message.content or "")
    if message.tool_calls:
        size += len(json.dumps(message.tool_calls, ensure_ascii=False))
    return size


def _blocks(history: list[Message]) -> list[list[Message]]:
    """带工具调用的助手消息和紧跟的工具结果算一块，避免裁掉一半。"""
    blocks: list[list[Message]] = []
    index = 0
    while index < len(history):
        message = history[index]
        if message.role == "assistant" and message.tool_calls:
            ids = {tc["id"] for tc in message.tool_calls}
            block = [message]
            index += 1
            while (
                index < len(history)
                and history[index].role == "tool"
                and history[index].tool_call_id in ids
            ):
                block.append(history[index])
                index += 1
            blocks.append(block)
            continue
        blocks.append([message])
        index += 1
    return blocks


def prune_history(
    history: list[Message], budget_chars: int = CONTEXT_CHAR_BUDGET
) -> tuple[list[Message], bool]:
    """从最近的消息往回保留，超出预算就丢掉更早的块。至少保留最后一块。"""
    blocks = _blocks(history)
    if not blocks:
        return [], False
    kept: list[list[Message]] = []
    used = 0
    for block in reversed(blocks):
        size = sum(_message_size(message) for message in block)
        if kept and used + size > budget_chars:
            break
        kept.append(block)
        used += size
    kept.reverse()
    omitted = len(kept) < len(blocks)
    return [message for block in kept for message in block], omitted


def to_llm_messages(
    system_prompt: str,
    history: list[Message],
    *,
    include_images: bool = True,
    workspace_root: Path | None = None,
) -> list[dict[str, Any]]:
    """把会话记录转成 Chat Completions 的消息列表。

    协议要求每个带 tool_calls 的 assistant 消息之后，紧跟每个调用对应的 tool 结果。
    被取消、中断或被新消息打断的调用没有结果，这里补上一条「未完成」结果，避免接口报错。
    """
    out: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    open_calls: list[str] = []

    def flush_open_calls() -> None:
        for call_id in open_calls:
            out.append({"role": "tool", "tool_call_id": call_id, "content": INTERRUPTED_RESULT})
        open_calls.clear()

    for m in history:
        if m.role == "tool":
            if m.tool_call_id in open_calls:
                open_calls.remove(m.tool_call_id)
                out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
            continue
        flush_open_calls()
        if m.role == "user":
            text = m.content
            if not text.strip() and m.skill_names and not m.attachments:
                text = "请按指定技能处理。"
            out.append(
                {
                    "role": "user",
                    "content": user_llm_content(
                        text,
                        m.attachments,
                        include_images=include_images,
                        workspace_root=workspace_root,
                        session_id=str(m.session_id),
                    ),
                }
            )
        elif m.role == "assistant":
            msg: dict[str, Any] = {"role": "assistant", "content": m.content or ""}
            if m.reasoning:
                msg["reasoning_content"] = m.reasoning
            if m.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in m.tool_calls
                ]
                open_calls.extend(tc["id"] for tc in m.tool_calls)
            out.append(msg)
    flush_open_calls()
    return out
