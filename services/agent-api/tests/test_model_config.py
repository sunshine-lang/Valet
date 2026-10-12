import pytest
from openai import AsyncOpenAI
from pydantic import ValidationError

from agent_api.agent.settings import AgentSettings, normalize_api_base
from agent_api.llm.providers import reasoning_params, resolve_credentials


def test_api_base_accepts_full_chat_completions_url():
    settings = AgentSettings(api_base="https://api.example.com/v1/chat/completions/")
    assert settings.api_base == "https://api.example.com/v1"
    assert normalize_api_base("https://dashscope.aliyuncs.com/compatible-mode/v1") == (
        "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )


def test_openai_reasoning_is_only_sent_for_reasoning_models():
    assert reasoning_params("gpt-4o", "high", "openai") == {}
    assert reasoning_params("o4-mini", "high", "openai") == {"reasoning_effort": "high"}
    assert reasoning_params("deepseek-chat", "off", "deepseek") == {
        "thinking": {"type": "disabled"}
    }


def test_resolve_credentials_uses_provider_default_base():
    key, base = resolve_credentials(provider="openai", api_base="", api_key="sk-test")
    assert key == "sk-test"
    assert base == "https://api.openai.com/v1"


def test_catalog_model_declares_tools_and_images():
    vision = AgentSettings(provider="openai", model="gpt-4o", image_input=False, tool_calling=False)
    assert vision.image_input is True
    assert vision.tool_calling is True
    assert vision.custom_protocol is False

    text_only = AgentSettings(model="deepseek-v4-flash-0731", image_input=True)
    assert text_only.image_input is False
    assert text_only.tool_calling is True


def test_custom_provider_keeps_manual_capabilities():
    settings = AgentSettings(
        provider="custom",
        model="my-model",
        api_base="https://example.com/v1",
        tool_calling=False,
        image_input=True,
        custom_protocol=True,
    )
    assert settings.tool_calling is False
    assert settings.image_input is True
    assert settings.custom_protocol is True


def test_unknown_provider_is_rejected():
    with pytest.raises(ValidationError):
        AgentSettings(provider="not-a-provider")


def test_api_key_is_omitted_from_public_and_snapshot():
    settings = AgentSettings(api_key="sk-secret", api_base="https://api.example.com/v1")
    assert "sk-secret" not in settings.public_dict().values()
    assert settings.public_dict()["api_key_set"] is True
    assert "api_key" not in settings.snapshot_dict()


async def test_blank_api_key_keeps_the_stored_one(client):
    current = (await client.get("/api/agent-config")).json()["config"]
    saved = await client.put("/api/agent-config", json={**current, "api_key": "sk-secret"})
    assert saved.json()["config"]["api_key_set"] is True
    assert "sk-secret" not in saved.text

    again = await client.put(
        "/api/agent-config",
        json={**saved.json()["config"], "model": "qwen3.8-max-0902"},
    )
    body = again.json()["config"]
    assert body["api_key_set"] is True
    assert body["model"] == "qwen3.8-max-0902"
    assert "api_key" not in body


async def test_model_client_supports_socks_proxy(monkeypatch):
    for name in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
        "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:1080")

    async with AsyncOpenAI(
        api_key="test-key",
        base_url="https://example.invalid/v1",
    ) as client:
        assert not client.is_closed()
