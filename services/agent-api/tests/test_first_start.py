import asyncio
from datetime import timedelta

import httpx
import pytest
from conftest import FakeLLM, finished_run, new_session, send, text
from sqlalchemy import func, select

from agent_api.agent.settings import AgentSettings
from agent_api.config import Settings
from agent_api.llm.openai_compat import OpenAICompatClient
from agent_api.main import build_llm, create_app
from agent_api.models import AgentConfig, Message, Run, ScheduledTask, utcnow
from agent_api.schedules import fire_due


@pytest.fixture
async def first_start(tmp_path):
    credentials = {name: "" for name in Settings.model_fields if name.endswith("_api_key")}
    env = Settings(
        _env_file=None,
        **credentials,
        dashscope_model="qwen3.8-flash",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'new-install' / 'valet.db'}",
        workspace_root=str(tmp_path / "workspace"),
        user_skills_dir=str(tmp_path / "skills"),
    )
    llm = FakeLLM()
    app = create_app(settings=env, llm=llm)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, app, llm, env


async def test_missing_configuration_starts_and_explains_setup(first_start):
    client, _, _, _ = first_start
    response = await client.get("/api/health")
    health = response.json()
    assert response.status_code == 200
    assert health["llm_configured"] is False
    assert health["model"] == "qwen3.8-flash"
    assert ".env" in health["setup_message"]
    assert "DASHSCOPE_API_KEY" in health["setup_message"]
    config = (await client.get("/api/agent-config")).json()["config"]
    assert config["model"] == "qwen3.8-flash"
    assert config["api_key_set"] is False
    assert "api_key" not in config
    providers = (await client.get("/api/providers")).json()
    assert next(row for row in providers if row["id"] == "dashscope")["env_key_set"] is False


async def test_missing_key_blocks_runs_and_schedules_without_model_calls(first_start):
    client, app, llm, _ = first_start
    session_id = await new_session(client)
    response = await client.post(
        f"/api/sessions/{session_id}/messages", json={"content": "你好"}
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "model_not_configured"
    assert "设置 → 模型" in response.json()["detail"]["message"]
    assert not llm.requests
    scheduled = await client.post("/api/schedules", json={"name": "测试", "prompt": "你好"})
    assert scheduled.status_code == 503
    async with app.state.db.sessionmaker() as session:
        assert await session.scalar(select(func.count(Run.id))) == 0
        assert await session.scalar(select(func.count(Message.id))) == 0
        assert await session.scalar(select(func.count(ScheduledTask.id))) == 0


async def test_saving_key_unblocks_same_process_and_keeps_key_private(first_start):
    client, _, llm, _ = first_start
    config = (await client.get("/api/agent-config")).json()["config"]
    response = await client.put(
        "/api/agent-config", json={**config, "api_key": "first-start-test-key"}
    )
    assert response.status_code == 200
    assert "first-start-test-key" not in response.text
    health = (await client.get("/api/health")).json()
    assert health["llm_configured"] is True
    assert health["setup_message"] is None
    llm.script(text("配置已生效"))
    run = finished_run(await send(client, await new_session(client), "你好"))
    assert run["status"] == "completed"
    assert "api_key" not in run["config_snapshot"]
    assert llm.requests[0].api_key == "first-start-test-key"
    assert llm.requests[0].model == "qwen3.8-flash"


async def test_environment_model_key_and_region_are_used(first_start):
    client, _, llm, env = first_start
    env.dashscope_api_key = "environment-test-key"
    env.dashscope_base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    assert (await client.get("/api/health")).json()["llm_configured"] is True
    providers = (await client.get("/api/providers")).json()
    assert next(row for row in providers if row["id"] == "dashscope")["base_url"] == (
        env.dashscope_base_url
    )
    llm.script(text("环境配置已生效"))
    await send(client, await new_session(client), "你好")
    assert llm.requests[0].api_key == "environment-test-key"
    assert llm.requests[0].base_url == env.dashscope_base_url
    assert llm.requests[0].model == env.dashscope_model


@pytest.mark.parametrize(
    "target",
    [
        {"provider": "openai", "model": "gpt-4o"},
        {"api_base": "https://different.example.test/v1"},
    ],
)
async def test_new_credential_target_cannot_inherit_old_key(first_start, target):
    client, _, llm, _ = first_start
    config = (await client.get("/api/agent-config")).json()["config"]
    saved = await client.put("/api/agent-config", json={**config, "api_key": "old-test-key"})
    changed = await client.put(
        "/api/agent-config", json={**saved.json()["config"], **target}
    )
    assert changed.json()["config"]["api_key_set"] is False
    assert (await client.get("/api/health")).json()["llm_configured"] is False
    response = await client.post(
        f"/api/sessions/{await new_session(client)}/messages", json={"content": "你好"}
    )
    assert response.status_code == 503
    assert not llm.requests


async def test_unconfigured_due_task_waits_until_credentials_are_saved(first_start):
    client, app, llm, _ = first_start
    due_at = utcnow() - timedelta(seconds=1)
    async with app.state.db.sessionmaker() as session:
        task = ScheduledTask(name="等待配置", prompt="你好", repeat="once", next_run_at=due_at)
        session.add(task)
        await session.commit()
        task_id = task.id
    assert await fire_due(app.state.db, app.state.runs) == 0
    async with app.state.db.sessionmaker() as session:
        task = await session.get(ScheduledTask, task_id)
        assert task.enabled is True
        assert task.next_run_at is not None
        assert task.last_run_at is None
    config = (await client.get("/api/agent-config")).json()["config"]
    await client.put("/api/agent-config", json={**config, "api_key": "schedule-test-key"})
    llm.script(text("配置完成后执行"))
    assert await fire_due(app.state.db, app.state.runs) == 1
    await asyncio.gather(*app.state.runs._tasks.values())
    async with app.state.db.sessionmaker() as session:
        assert await session.scalar(select(func.count(Run.id))) == 1


async def test_retired_simulated_tools_are_removed_from_legacy_config(first_start):
    client, app, _, _ = first_start
    data = AgentSettings(
        enabled_tools=["calculator", "slow_task", "send_notification"]
    ).model_dump()
    async with app.state.db.sessionmaker() as session:
        session.add(AgentConfig(id=1, data=data))
        await session.commit()
    assert (await client.get("/api/agent-config")).json()["config"]["enabled_tools"] == [
        "calculator"
    ]
    saved = await client.put("/api/agent-config", json=data)
    assert saved.status_code == 200
    assert saved.json()["config"]["enabled_tools"] == ["calculator"]


async def test_legacy_mock_environment_never_creates_a_mock_client(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    settings = Settings(_env_file=None, dashscope_api_key="")
    client = build_llm(settings)
    assert isinstance(client, OpenAICompatClient)
    await client._client.close()
