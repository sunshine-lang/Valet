import asyncio
import json
import time

from conftest import call, finished_run, new_session, parse_sse, run_steps, send, text

from agent_api.llm import LLMResult, ToolCall


async def test_final_answer_without_tools(client, fake_llm):
    fake_llm.script(text("你好！"))
    sid = await new_session(client)

    events = await send(client, sid, "你好")

    names = [n for n, _ in events]
    assert names[0] == "run.started"
    assert "message.delta" in names
    run = finished_run(events)
    assert run["status"] == "completed"
    assert run["stop_reason"] == "final_answer"
    assert run["llm_calls"] == 1
    assert run["input_tokens"] == 100
    assert run["cost_cny"] is not None
    assert run["config_snapshot"]["model"] == "deepseek-v4-flash-0731"


async def test_tool_success_then_answer(client, fake_llm):
    fake_llm.script(call("calculator", {"expression": "(3+4)*2"}), text("结果是 14"))
    sid = await new_session(client)

    run = finished_run(await send(client, sid, "算一下 (3+4)*2"))

    steps = await run_steps(client, run["id"])
    assert [(s["type"], s["status"]) for s in steps] == [
        ("llm_call", "ok"),
        ("tool_call", "ok"),
        ("llm_call", "ok"),
    ]
    assert steps[1]["output"] == {"expression": "(3+4)*2", "result": 14}
    assert steps[1]["attributes"]["gen_ai.tool.name"] == "calculator"
    second_request = fake_llm.requests[1].messages
    assert second_request[-1]["role"] == "tool"
    assert json.loads(second_request[-1]["content"])["result"] == 14


async def test_invalid_arguments_are_fed_back(client, fake_llm):
    fake_llm.script(
        call("slow_task", {"seconds": 999}),
        call("slow_task", {"seconds": 0}, call_id="call_2"),
        text("好了"),
    )
    sid = await new_session(client)

    run = finished_run(await send(client, sid, "跑一个慢任务"))

    steps = await run_steps(client, run["id"])
    assert steps[1]["status"] == "error"
    assert steps[1]["output"]["error"] == "invalid_arguments"
    fed_back = json.loads(fake_llm.requests[1].messages[-1]["content"])
    assert fed_back["error"] == "invalid_arguments"
    assert steps[3]["status"] == "ok"


async def test_tool_timeout(client, fake_llm, monkeypatch):
    from agent_api.tools.probes import SlowTask

    monkeypatch.setattr(SlowTask, "timeout_s", 0.05)
    fake_llm.script(call("slow_task", {"seconds": 1}), text("超时了"))
    sid = await new_session(client)

    run = finished_run(await send(client, sid, "慢任务"))

    steps = await run_steps(client, run["id"])
    assert steps[1]["status"] == "timeout"
    assert run["status"] == "completed"


async def test_consecutive_failures_stop_the_loop(client, fake_llm):
    fail = {"mode": "fail"}
    fake_llm.script(
        call("flaky_task", fail, "c1"),
        call("flaky_task", fail, "c2"),
        call("flaky_task", fail, "c3"),
        text("抱歉，工具一直失败"),
    )
    sid = await new_session(client)

    run = finished_run(await send(client, sid, "跑一下"))

    assert run["status"] == "failed"
    assert run["stop_reason"] == "consecutive_tool_failures"
    steps = await run_steps(client, run["id"])
    assert any(s["type"] == "guardrail" and s["name"] == "consecutive_failures" for s in steps)
    assert fake_llm.requests[-1].tools == []


async def _put_config(client, **overrides):
    current = (await client.get("/api/agent-config")).json()["config"]
    await client.put("/api/agent-config", json={**current, **overrides})


async def test_active_stream_is_not_cut_by_run_budget(client, fake_llm):
    await _put_config(client, run_timeout_s=1, stream_idle_s=30)
    fake_llm.delay_s = 1.2
    fake_llm.script(text("想完了"))
    sid = await new_session(client)

    run = finished_run(await send(client, sid, "想一下"))

    assert run["status"] == "completed"
    assert run["stop_reason"] == "final_answer"


async def test_time_budget_wraps_up_after_the_current_turn(client, fake_llm):
    await _put_config(client, run_timeout_s=1, stream_idle_s=30)
    fake_llm.script(call("slow_task", {"seconds": 1.2}), text("先说到这"))
    sid = await new_session(client)

    run = finished_run(await send(client, sid, "做一件慢事"))

    assert run["status"] == "completed"
    assert run["stop_reason"] == "run_timeout"
    assert fake_llm.requests[-1].tools == []
    steps = await run_steps(client, run["id"])
    assert any(s["type"] == "guardrail" and s["name"] == "run_timeout" for s in steps)


async def test_time_budget_without_answer_fails(client, fake_llm):
    await _put_config(client, run_timeout_s=1, stream_idle_s=30)
    fake_llm.script(call("slow_task", {"seconds": 1.2}), text("  "))
    sid = await new_session(client)

    run = finished_run(await send(client, sid, "做一件慢事"))

    assert run["status"] == "failed"
    assert run["stop_reason"] == "run_timeout"


async def test_stream_idle_keeps_partial_answer(client, fake_llm):
    await _put_config(client, stream_idle_s=1)
    fake_llm.pause_s = 30
    fake_llm.pause_after_chars = 1
    fake_llm.script(text("你好世界"))
    sid = await new_session(client)
    started = time.perf_counter()

    events = await send(client, sid, "你好")

    assert time.perf_counter() - started < 5
    run = finished_run(events)
    assert run["status"] == "completed"
    assert run["stop_reason"] == "stream_idle"
    assert "".join(data["text"] for name, data in events if name == "message.delta") == "你"


async def test_stream_idle_without_text_fails(client, fake_llm):
    await _put_config(client, stream_idle_s=1)
    fake_llm.pause_s = 30
    fake_llm.script(text(""))
    sid = await new_session(client)

    run = finished_run(await send(client, sid, "你好"))

    assert run["status"] == "failed"
    assert run["stop_reason"] == "stream_idle"
    assert "没有新输出" in (run["error"] or "")


async def test_max_steps(client, fake_llm):
    await client.put(
        "/api/agent-config",
        json={**(await client.get("/api/agent-config")).json()["config"], "max_steps": 2},
    )
    fake_llm.script(
        call("get_current_time", {}, "c1"),
        call("get_current_time", {}, "c2"),
        text("先到这里"),
    )
    sid = await new_session(client)

    run = finished_run(await send(client, sid, "一直查时间"))

    assert run["stop_reason"] == "max_steps"
    assert run["config_snapshot"]["max_steps"] == 2


async def test_confirmation_approved(client, fake_llm):
    args = {"recipient": "张三", "message": "开会"}
    fake_llm.script(call("send_notification", args, "n1"), text("已发送"))
    sid = await new_session(client)

    events = await send(client, sid, "通知张三开会")

    run = finished_run(events)
    assert run["status"] == "awaiting_confirmation"
    req = next(d for n, d in events if n == "confirmation.required")
    assert req["tool_call_id"] == "n1"
    detail = (await client.get(f"/api/sessions/{sid}")).json()
    assert detail["pending_confirmation"]["tool_call_id"] == "n1"

    resp = await client.post(
        f"/api/runs/{run['id']}/confirm", json={"tool_call_id": "n1", "approved": True}
    )
    resumed = finished_run(parse_sse(resp.text))
    assert resumed["status"] == "completed"
    steps = await run_steps(client, run["id"])
    assert [(s["type"], s["name"], s["status"]) for s in steps] == [
        ("llm_call", "deepseek-v4-flash-0731", "ok"),
        ("guardrail", "confirmation_required", "approved"),
        ("tool_call", "send_notification", "ok"),
        ("llm_call", "deepseek-v4-flash-0731", "ok"),
    ]


async def test_confirmation_rejected(client, fake_llm):
    fake_llm.script(
        call("send_notification", {"recipient": "李四", "message": "hi"}, "n1"),
        text("好的，不发了"),
    )
    sid = await new_session(client)
    run = finished_run(await send(client, sid, "通知李四"))

    resp = await client.post(
        f"/api/runs/{run['id']}/confirm", json={"tool_call_id": "n1", "approved": False}
    )

    assert finished_run(parse_sse(resp.text))["status"] == "completed"
    steps = await run_steps(client, run["id"])
    assert not any(s["type"] == "tool_call" for s in steps)
    fed_back = json.loads(fake_llm.requests[-1].messages[-1]["content"])
    assert fed_back["error"] == "rejected_by_user"


async def test_new_message_supersedes_pending_confirmation(client, fake_llm):
    fake_llm.script(
        call("send_notification", {"recipient": "王五", "message": "hi"}, "n1"), text("换个话题")
    )
    sid = await new_session(client)
    first = finished_run(await send(client, sid, "通知王五"))

    second = finished_run(await send(client, sid, "算了，不用了"))

    assert second["status"] == "completed"
    runs = (await client.get(f"/api/sessions/{sid}")).json()["runs"]
    assert runs[0]["id"] == first["id"]
    assert runs[0]["stop_reason"] == "superseded"
    tool_msgs = [m for m in fake_llm.requests[-1].messages if m["role"] == "tool"]
    assert json.loads(tool_msgs[0]["content"])["error"] == "interrupted"


async def test_cancel_running_run(client, fake_llm):
    fake_llm.delay_s = 5
    fake_llm.script(text("不会出现"))
    sid = await new_session(client)

    task = asyncio.create_task(send(client, sid, "慢慢想"))
    for _ in range(50):
        await asyncio.sleep(0.02)
        runs = (await client.get("/api/runs", params={"session_id": sid})).json()["items"]
        if runs:
            break
    resp = await client.post(f"/api/runs/{runs[0]['id']}/cancel")
    assert resp.json() == {"cancelled": True}

    run = finished_run(await task)
    assert run["status"] == "cancelled"
    steps = await run_steps(client, run["id"])
    assert steps[0]["status"] == "cancelled"


async def test_disabled_tool_is_blocked(client, fake_llm):
    config = (await client.get("/api/agent-config")).json()["config"]
    config["enabled_tools"] = ["calculator"]
    await client.put("/api/agent-config", json=config)
    fake_llm.script(call("get_current_time", {}), text("没法查时间"))
    sid = await new_session(client)

    run = finished_run(await send(client, sid, "几点了"))

    steps = await run_steps(client, run["id"])
    assert steps[1]["type"] == "guardrail"
    assert steps[1]["status"] == "blocked"
    assert [t["function"]["name"] for t in fake_llm.requests[0].tools] == ["calculator"]


async def test_tool_batch_runs_in_parallel(client, fake_llm, monkeypatch):
    async def slow(self, args, ctx):
        await asyncio.sleep(0.4)
        return {"ok": True}

    monkeypatch.setattr("agent_api.tools.probes.Calculator.run", slow)
    monkeypatch.setattr("agent_api.tools.probes.GetCurrentTime.run", slow)
    fake_llm.script(
        LLMResult(
            tool_calls=[
                ToolCall("c1", "calculator", '{"expression": "1+1"}'),
                ToolCall("c2", "get_current_time", "{}"),
            ],
            finish_reason="tool_calls",
            input_tokens=10,
            output_tokens=10,
        ),
        text("都好了"),
    )
    sid = await new_session(client)
    started = time.perf_counter()
    run = finished_run(await send(client, sid, "一起做"))
    elapsed = time.perf_counter() - started
    assert elapsed < 0.7
    steps = await run_steps(client, run["id"])
    assert [step["name"] for step in steps if step["type"] == "tool_call"] == [
        "calculator",
        "get_current_time",
    ]


async def test_message_during_run_is_steered(client, fake_llm):
    fake_llm.delay_s = 0.8
    fake_llm.script(text("第一句"), text("第二句"))
    sid = await new_session(client)
    task = asyncio.create_task(send(client, sid, "先说"))
    await asyncio.sleep(0.2)
    resp = await client.post(f"/api/sessions/{sid}/messages", json={"content": "插一句"})
    assert resp.status_code == 200
    assert resp.json()["queued"] is True
    run = finished_run(await task)
    assert run["llm_calls"] == 2
    assert "插一句" in fake_llm.requests[1].messages[-1]["content"]
