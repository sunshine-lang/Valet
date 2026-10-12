import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from agent_api.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(dt: datetime) -> datetime:
    # SQLite 读回的是不带时区的时间
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(120), default="新对话")
    # 本对话已经允许的动作类别：read、write、network、command。
    permission_grants: Mapped[list] = mapped_column(JSON, default=list)
    # ask 始终询问联网和项目外文件；assist 只询问风险操作；full 不再询问这两类。
    permission_mode: Mapped[str] = mapped_column(String(16), default="assist")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Message(Base):
    """模型视角的对话记录：重建上下文时按 seq 顺序原样回放。"""

    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_session_seq", "session_id", "seq", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE")
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))  # user | assistant | tool
    content: Mapped[str] = mapped_column(Text, default="")
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 用户上传的图片和文件。text 是正文摘录，原始字节在磁盘上。
    attachments: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    # 用户在这一轮点名使用的技能。正文在运行时再读，不写进消息文本。
    skill_names: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Run(Base):
    """一次运行 = 用户发一条消息后，智能体直到给出最终回复（或暂停、失败）为止的全过程。"""

    __tablename__ = "runs"
    __table_args__ = (Index("ix_runs_started_at", "started_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    # running | awaiting_confirmation | completed | failed | cancelled
    status: Mapped[str] = mapped_column(String(32), default="running")
    stop_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_text: Mapped[str] = mapped_column(Text, default="")
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_cny: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Step(Base):
    """运行中的一步：一次模型调用、一次工具调用或一次护栏判定。"""

    __tablename__ = "steps"
    __table_args__ = (Index("ix_steps_run_seq", "run_id", "seq", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(16))  # llm_call | tool_call | guardrail
    name: Mapped[str] = mapped_column(String(64))
    # running | ok | error | timeout | cancelled | blocked | pending | approved | rejected
    status: Mapped[str] = mapped_column(String(16), default="running")
    input: Mapped[Any] = mapped_column(JSON, nullable=True)
    output: Mapped[Any] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_cny: Mapped[float | None] = mapped_column(Float, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ScheduledTask(Base):
    """到点后用提示词新开一轮对话。时间按界面时区理解。"""

    __tablename__ = "scheduled_tasks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80))
    prompt: Mapped[str] = mapped_column(Text, default="")
    effort: Mapped[str] = mapped_column(String(16), default="high")
    # interval | once | daily | weekly | biweekly | monthly | yearly
    repeat: Mapped[str] = mapped_column(String(16), default="daily")
    interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    hour: Mapped[int] = mapped_column(Integer, default=9)
    minute: Mapped[int] = mapped_column(Integer, default=0)
    second: Mapped[int] = mapped_column(Integer, default=0)
    weekday: Mapped[int] = mapped_column(Integer, default=0)  # 0 = 周一，兼容旧数据
    weekdays: Mapped[list] = mapped_column(JSON, default=list)  # 每周 / 每双周可多选
    month_day: Mapped[int] = mapped_column(Integer, default=1)
    month: Mapped[int] = mapped_column(Integer, default=1)
    once_on: Mapped[str | None] = mapped_column(String(10), nullable=True)
    valid_from: Mapped[str | None] = mapped_column(String(10), nullable=True)
    valid_until: Mapped[str | None] = mapped_column(String(10), nullable=True)
    notify_wechat: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_session_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentConfig(Base):
    """当前生效的智能体配置（单行）。每次运行开始时复制一份到 Run.config_snapshot。"""

    __tablename__ = "agent_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
