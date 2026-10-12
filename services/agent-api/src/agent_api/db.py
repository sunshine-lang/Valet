from collections.abc import AsyncIterator

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def _add_missing_columns(connection) -> None:
    """create_all 不会给已有表加列。这些字段是后加上的。"""
    columns = {column["name"] for column in inspect(connection).get_columns("messages")}
    if "reasoning" not in columns:
        connection.execute(text("ALTER TABLE messages ADD COLUMN reasoning TEXT"))
    if "attachments" not in columns:
        connection.execute(text("ALTER TABLE messages ADD COLUMN attachments JSON"))
    if "skill_names" not in columns:
        connection.execute(text("ALTER TABLE messages ADD COLUMN skill_names JSON"))
    tables = set(inspect(connection).get_table_names())
    if "chat_sessions" in tables:
        session_columns = {
            column["name"] for column in inspect(connection).get_columns("chat_sessions")
        }
        if "permission_grants" not in session_columns:
            connection.execute(text("ALTER TABLE chat_sessions ADD COLUMN permission_grants JSON"))
        if "permission_mode" not in session_columns:
            connection.execute(
                text(
                    "ALTER TABLE chat_sessions ADD COLUMN permission_mode "
                    "VARCHAR(16) DEFAULT 'assist'"
                )
            )
    if "scheduled_tasks" not in tables:
        return
    schedule_columns = {
        column["name"] for column in inspect(connection).get_columns("scheduled_tasks")
    }
    if "second" not in schedule_columns:
        connection.execute(text("ALTER TABLE scheduled_tasks ADD COLUMN second INTEGER DEFAULT 0"))
    if "weekdays" not in schedule_columns:
        connection.execute(text("ALTER TABLE scheduled_tasks ADD COLUMN weekdays JSON"))
    if "once_on" not in schedule_columns:
        connection.execute(text("ALTER TABLE scheduled_tasks ADD COLUMN once_on VARCHAR(10)"))


class Database:
    def __init__(self, url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(url, pool_pre_ping=True)
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_all(self) -> None:
        from agent_api import models  # noqa: F401  # registers tables on Base.metadata

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(_add_missing_columns)

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessionmaker() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()
