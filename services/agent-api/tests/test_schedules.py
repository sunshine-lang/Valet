from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from agent_api.schedules import compute_next

TZ = ZoneInfo("Asia/Shanghai")


def _next(**kwargs):
    base = dict(
        repeat="daily",
        interval_minutes=60,
        hour=10,
        minute=44,
        weekday=0,
        month_day=1,
        month=1,
        valid_from=None,
        valid_until=None,
        after=datetime(2026, 10, 11, 1, 0, tzinfo=UTC),  # 上海 09:00
        tz=TZ,
    )
    base.update(kwargs)
    return compute_next(**base)


def test_daily_uses_later_today():
    moment = _next()
    local = moment.astimezone(TZ)
    assert (local.year, local.month, local.day, local.hour, local.minute) == (2026, 10, 11, 10, 44)


def test_daily_rolls_to_tomorrow_after_the_clock():
    moment = _next(after=datetime(2026, 10, 11, 3, 0, tzinfo=UTC))  # 上海 11:00
    local = moment.astimezone(TZ)
    assert (local.day, local.hour, local.minute) == (12, 10, 44)


def test_weekly_uses_the_nearest_selected_weekday():
    # 2026-10-11 是周日，勾选周三和周日，当天 10:44 还没到
    moment = _next(repeat="weekly", weekday=6, weekdays=[2, 6])
    local = moment.astimezone(TZ)
    assert local.weekday() == 6
    assert local.day == 11


def test_once_ignores_a_validity_window_that_excludes_the_day():
    moment = _next(
        repeat="once",
        once_on="2026-10-11",
        hour=13,
        minute=47,
        valid_from="2026-11-10",
        valid_until="2026-11-20",
    )
    local = moment.astimezone(TZ)
    assert (local.month, local.day, local.hour, local.minute) == (10, 11, 13, 47)


def test_once_uses_the_chosen_date():
    moment = _next(repeat="once", once_on="2026-10-20", hour=12, minute=57, second=8)
    local = moment.astimezone(TZ)
    assert (local.year, local.month, local.day, local.hour, local.minute, local.second) == (
        2026,
        10,
        20,
        12,
        57,
        8,
    )


def test_weekly_skips_to_next_monday():
    # 2026-10-11 是周日
    moment = _next(repeat="weekly", weekday=0)
    local = moment.astimezone(TZ)
    assert local.weekday() == 0
    assert local.day == 12


def test_validity_stops_after_the_end_date():
    assert (
        _next(
            after=datetime(2026, 10, 11, 3, 0, tzinfo=UTC),
            valid_until="2026-10-11",
        )
        is None
    )


async def test_create_list_and_delete(client):
    created = await client.post(
        "/api/schedules",
        json={"name": "日报", "prompt": "总结今天", "repeat": "daily", "hour": 9, "minute": 0},
    )
    assert created.status_code == 201
    task_id = created.json()["id"]
    assert created.json()["next_run_at"]
    listed = (await client.get("/api/schedules")).json()
    assert any(item["id"] == task_id for item in listed)
    assert (await client.delete(f"/api/schedules/{task_id}")).status_code == 204


def test_interval_respects_minimum_gap():
    moment = _next(repeat="interval", interval_minutes=5)
    assert moment - datetime(2026, 10, 11, 1, 0, tzinfo=UTC) == timedelta(minutes=5)
