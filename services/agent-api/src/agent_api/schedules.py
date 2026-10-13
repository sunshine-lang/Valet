"""定时任务：算出下一次触发时间，到点新开一轮对话。"""

import asyncio
import contextlib
import logging
import uuid
from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from agent_api.agent.runs import EventStream, RunManager
from agent_api.config import get_settings
from agent_api.db import Database
from agent_api.llm.providers import ModelConfigurationError
from agent_api.models import ChatSession, ScheduledTask, as_utc, utcnow
from agent_api.tracing.recorder import iso_utc

log = logging.getLogger(__name__)

REPEATS = ("interval", "once", "daily", "weekly", "biweekly", "monthly", "yearly")
EFFORTS = ("off", "low", "medium", "high", "max")
TICK_S = 20


def local_zone() -> ZoneInfo:
    return ZoneInfo(get_settings().display_timezone)


def _parse_day(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _at(day: date, hour: int, minute: int, tz: ZoneInfo, second: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=tz)


def _selected_weekdays(weekday: int, weekdays: list[int] | None) -> list[int]:
    chosen = sorted({int(day) for day in (weekdays or []) if 0 <= int(day) <= 6})
    return chosen or [weekday % 7]


def _clamp_day(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, monthrange(year, month)[1]))


def compute_next(
    *,
    repeat: str,
    interval_minutes: int,
    hour: int,
    minute: int,
    weekday: int,
    month_day: int,
    month: int,
    valid_from: str | None,
    valid_until: str | None,
    after: datetime,
    tz: ZoneInfo | None = None,
    weekdays: list[int] | None = None,
    second: int = 0,
    once_on: str | None = None,
) -> datetime | None:
    """下一次触发时刻。`after` 之后的第一档；超出有效期则没有下一次。"""
    tz = tz or local_zone()
    after = as_utc(after)
    local = after.astimezone(tz)
    start = _parse_day(valid_from)
    end = _parse_day(valid_until)

    def accept(moment: datetime) -> datetime | None:
        day = moment.astimezone(tz).date()
        if start and day < start:
            return None
        if end and day > end:
            return None
        if moment <= after:
            return None
        return moment.astimezone(UTC)

    if repeat == "interval":
        step = timedelta(minutes=max(5, interval_minutes))
        moment = after + step
        if start:
            opening = _at(start, 0, 0, tz).astimezone(UTC)
            if moment < opening:
                moment = opening + step
        return accept(moment)

    if repeat == "once":
        chosen = _parse_day(once_on)
        if chosen:
            # 单次的日期时间就是触发点，不再被另一段有效期挡掉。
            moment = _at(chosen, hour, minute, tz, second).astimezone(UTC)
            return moment if moment > after else None
        day = start or local.date()
        moment = _at(day, hour, minute, tz, second)
        if moment.astimezone(UTC) <= after:
            if start:
                return None
            moment = _at(day + timedelta(days=1), hour, minute, tz, second)
        return accept(moment)

    if repeat == "daily":
        day = local.date()
        moment = _at(day, hour, minute, tz, second)
        if moment.astimezone(UTC) <= after:
            moment = _at(day + timedelta(days=1), hour, minute, tz, second)
        if start and moment.astimezone(tz).date() < start:
            probe = _at(start, hour, minute, tz, second)
            if probe.astimezone(UTC) <= after:
                probe = _at(start + timedelta(days=1), hour, minute, tz, second)
            moment = probe
        return accept(moment)

    if repeat in {"weekly", "biweekly"}:
        chosen = _selected_weekdays(weekday, weekdays)
        anchor = start or date(2024, 1, 1)
        anchor_monday = anchor - timedelta(days=anchor.weekday())
        begin = local.date()
        if start and start > begin:
            begin = start
        for offset in range(0, 370):
            day = begin + timedelta(days=offset)
            if day.weekday() not in chosen:
                continue
            if repeat == "biweekly":
                monday = day - timedelta(days=day.weekday())
                if ((monday - anchor_monday).days // 7) % 2 != 0:
                    continue
            picked = accept(_at(day, hour, minute, tz, second))
            if picked:
                return picked
        return None

    if repeat == "monthly":
        year, mon = local.year, local.month
        for _ in range(24):
            day = _clamp_day(year, mon, month_day)
            moment = _at(day, hour, minute, tz, second)
            picked = accept(moment)
            if picked:
                return picked
            mon += 1
            if mon == 13:
                mon = 1
                year += 1
        return None

    if repeat == "yearly":
        year = local.year
        for _ in range(5):
            day = _clamp_day(year, month, month_day)
            moment = _at(day, hour, minute, tz, second)
            picked = accept(moment)
            if picked:
                return picked
            year += 1
        return None

    return None


def serialize_task(task: ScheduledTask) -> dict:
    return {
        "id": str(task.id),
        "name": task.name,
        "prompt": task.prompt,
        "effort": task.effort,
        "repeat": task.repeat,
        "interval_minutes": task.interval_minutes,
        "hour": task.hour,
        "minute": task.minute,
        "second": task.second or 0,
        "weekday": task.weekday,
        "weekdays": list(task.weekdays or []),
        "once_on": task.once_on,
        "month_day": task.month_day,
        "month": task.month,
        "valid_from": task.valid_from,
        "valid_until": task.valid_until,
        "notify_wechat": task.notify_wechat,
        "enabled": task.enabled,
        "next_run_at": iso_utc(task.next_run_at) if task.next_run_at else None,
        "last_run_at": iso_utc(task.last_run_at) if task.last_run_at else None,
        "last_session_id": str(task.last_session_id) if task.last_session_id else None,
        "created_at": iso_utc(task.created_at),
    }


def _task_kwargs(task: ScheduledTask) -> dict:
    return {
        "repeat": task.repeat,
        "interval_minutes": task.interval_minutes,
        "hour": task.hour,
        "minute": task.minute,
        "second": task.second or 0,
        "weekday": task.weekday,
        "weekdays": list(task.weekdays or []),
        "month_day": task.month_day,
        "month": task.month,
        "once_on": task.once_on,
        "valid_from": task.valid_from,
        "valid_until": task.valid_until,
    }


def apply_schedule(task: ScheduledTask, after: datetime | None = None) -> None:
    task.next_run_at = (
        compute_next(**_task_kwargs(task), after=after or utcnow()) if task.enabled else None
    )


async def _drain(stream: EventStream) -> None:
    with contextlib.suppress(Exception):
        async for _chunk in stream.sse():
            pass


async def fire_due(db: Database, manager: RunManager, now: datetime | None = None) -> int:
    """触发所有已到点的任务。返回实际发起的次数。"""
    try:
        await manager.configured_settings()
    except ModelConfigurationError:
        return 0
    moment = as_utc(now or utcnow())
    async with db.sessionmaker() as session:
        due = list(
            await session.scalars(
                select(ScheduledTask).where(
                    ScheduledTask.enabled.is_(True),
                    ScheduledTask.next_run_at.is_not(None),
                    ScheduledTask.next_run_at <= moment,
                )
            )
        )
        ids = [task.id for task in due]
    fired = 0
    for task_id in ids:
        if await _fire_one(db, manager, task_id, moment):
            fired += 1
    return fired


async def _fire_one(db: Database, manager: RunManager, task_id: uuid.UUID, now: datetime) -> bool:
    async with db.sessionmaker() as session:
        task = await session.get(ScheduledTask, task_id)
        if task is None or not task.enabled or task.next_run_at is None:
            return False
        if as_utc(task.next_run_at) > now:
            return False
        prompt = task.prompt.strip()
        effort = task.effort
        name = task.name.strip() or "定时任务"
        if task.repeat == "once":
            task.enabled = False
            task.next_run_at = None
        else:
            following = compute_next(**_task_kwargs(task), after=now)
            task.next_run_at = following
            if following is None:
                task.enabled = False
        task.last_run_at = now
        task.updated_at = now
        chat = ChatSession(title=name[:40])
        session.add(chat)
        await session.flush()
        task.last_session_id = chat.id
        await session.commit()
        session_id = chat.id

    if not prompt:
        return False
    try:
        result = await manager.start(session_id, prompt, effort=effort)
    except Exception:
        log.exception("定时任务 %s 启动失败", task_id)
        return False
    if isinstance(result, EventStream):
        asyncio.create_task(_drain(result))
    async with db.sessionmaker() as session:
        chat = await session.get(ChatSession, session_id)
        if chat is not None:
            chat.title = name[:40]
            await session.commit()
    return True


class ScheduleClock:
    def __init__(self, db: Database, manager: RunManager) -> None:
        self.db = db
        self.manager = manager
        self._stopped = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stopped.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _loop(self) -> None:
        while not self._stopped.is_set():
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=TICK_S)
                return
            except TimeoutError:
                pass
            try:
                await fire_due(self.db, self.manager)
            except Exception:
                log.exception("定时任务轮询失败")
