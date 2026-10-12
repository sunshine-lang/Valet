"""模型供应商。

每个供应商自己带接口地址、环境变量里的密钥和一份模型目录，调用走 OpenAI Chat Completions。
自定义供应商则由用户填写地址和模型 ID。结构参照 pi 的 provider：id、名称、base URL、鉴权、模型列表。
"""

from dataclasses import dataclass
from typing import Any, Literal

from agent_api.config import get_settings

ReasoningStyle = Literal["dashscope", "deepseek", "openai", "none", "auto"]


@dataclass(frozen=True)
class ModelInfo:
    id: str
    label: str
    description: str = ""
    # 元 / 百万 token。没有标价的供应商记 None，追踪里费用为 0。
    input_price: float | None = None
    output_price: float | None = None
    # 目录里的模型自己声明能力，普通配置不再让用户勾选。
    tools: bool = True
    image: bool = False


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    name: str
    base_url: str
    env_attr: str
    env_key: str
    reasoning: ReasoningStyle
    models: tuple[ModelInfo, ...]


def _m(
    model_id: str,
    label: str,
    description: str = "",
    *,
    image: bool = False,
    tools: bool = True,
) -> ModelInfo:
    return ModelInfo(model_id, label, description, tools=tools, image=image)


PROVIDERS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        id="dashscope",
        name="阿里云百炼",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        env_attr="dashscope_api_key",
        env_key="DASHSCOPE_API_KEY",
        reasoning="dashscope",
        models=(
            ModelInfo("deepseek-v4-flash-0731", "DeepSeek V4 Flash 0731", "默认", 1.0, 2.0),
            ModelInfo(
                "qwen3.8-max-0902", "Qwen3.8 Max 0902", "效果上限，可看图", 12.0, 36.0, image=True
            ),
            ModelInfo(
                "deepseek-v4.1-flash",
                "DeepSeek V4.1 Flash",
                "忙时价；闲时输入 1 / 输出 4",
                2.0,
                8.0,
            ),
        ),
    ),
    ProviderSpec(
        id="deepseek",
        name="DeepSeek",
        base_url="https://api.deepseek.com",
        env_attr="deepseek_api_key",
        env_key="DEEPSEEK_API_KEY",
        reasoning="deepseek",
        models=(
            _m("deepseek-chat", "DeepSeek Chat"),
            _m("deepseek-reasoner", "DeepSeek Reasoner"),
        ),
    ),
    ProviderSpec(
        id="moonshotai-cn",
        name="Moonshot（中国）",
        base_url="https://api.moonshot.cn/v1",
        env_attr="moonshot_api_key",
        env_key="MOONSHOT_API_KEY",
        reasoning="none",
        models=(
            _m("moonshot-v1-128k", "Moonshot 128K"),
            _m("moonshot-v1-32k", "Moonshot 32K"),
            _m("kimi-latest", "Kimi Latest", image=True),
        ),
    ),
    ProviderSpec(
        id="moonshotai",
        name="Moonshot",
        base_url="https://api.moonshot.ai/v1",
        env_attr="moonshot_api_key",
        env_key="MOONSHOT_API_KEY",
        reasoning="none",
        models=(
            _m("moonshot-v1-128k", "Moonshot 128K"),
            _m("kimi-latest", "Kimi Latest", image=True),
        ),
    ),
    ProviderSpec(
        id="zai",
        name="智谱",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        env_attr="zai_api_key",
        env_key="ZAI_API_KEY",
        reasoning="none",
        models=(
            _m("glm-4.5", "GLM-4.5"),
            _m("glm-4.5-flash", "GLM-4.5 Flash"),
            _m("glm-4-plus", "GLM-4 Plus"),
        ),
    ),
    ProviderSpec(
        id="minimax",
        name="MiniMax",
        base_url="https://api.minimaxi.com/v1",
        env_attr="minimax_api_key",
        env_key="MINIMAX_API_KEY",
        reasoning="none",
        models=(
            _m("MiniMax-M1", "MiniMax M1"),
            _m("MiniMax-Text-01", "MiniMax Text"),
        ),
    ),
    ProviderSpec(
        id="openai",
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        env_attr="openai_api_key",
        env_key="OPENAI_API_KEY",
        reasoning="openai",
        models=(
            _m("gpt-4.1", "GPT-4.1", image=True),
            _m("gpt-4.1-mini", "GPT-4.1 mini", image=True),
            _m("gpt-4o", "GPT-4o", image=True),
            _m("o4-mini", "o4-mini", image=True),
            _m("o3", "o3", image=True),
        ),
    ),
    ProviderSpec(
        id="google",
        name="Google",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        env_attr="gemini_api_key",
        env_key="GEMINI_API_KEY",
        reasoning="none",
        models=(
            _m("gemini-2.5-pro", "Gemini 2.5 Pro", image=True),
            _m("gemini-2.5-flash", "Gemini 2.5 Flash", image=True),
        ),
    ),
    ProviderSpec(
        id="xai",
        name="xAI",
        base_url="https://api.x.ai/v1",
        env_attr="xai_api_key",
        env_key="XAI_API_KEY",
        reasoning="none",
        models=(
            _m("grok-4", "Grok 4", image=True),
            _m("grok-3", "Grok 3"),
        ),
    ),
    ProviderSpec(
        id="groq",
        name="Groq",
        base_url="https://api.groq.com/openai/v1",
        env_attr="groq_api_key",
        env_key="GROQ_API_KEY",
        reasoning="none",
        models=(
            _m("llama-3.3-70b-versatile", "Llama 3.3 70B"),
            _m("openai/gpt-oss-20b", "GPT-OSS 20B"),
        ),
    ),
    ProviderSpec(
        id="mistral",
        name="Mistral",
        base_url="https://api.mistral.ai/v1",
        env_attr="mistral_api_key",
        env_key="MISTRAL_API_KEY",
        reasoning="none",
        models=(
            _m("mistral-large-latest", "Mistral Large"),
            _m("mistral-small-latest", "Mistral Small"),
        ),
    ),
    ProviderSpec(
        id="openrouter",
        name="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        env_attr="openrouter_api_key",
        env_key="OPENROUTER_API_KEY",
        reasoning="none",
        models=(
            _m("openai/gpt-4.1", "OpenAI GPT-4.1", image=True),
            _m("anthropic/claude-sonnet-4", "Claude Sonnet 4", image=True),
            _m("google/gemini-2.5-pro", "Gemini 2.5 Pro", image=True),
            _m("deepseek/deepseek-chat", "DeepSeek Chat"),
        ),
    ),
    ProviderSpec(
        id="cerebras",
        name="Cerebras",
        base_url="https://api.cerebras.ai/v1",
        env_attr="cerebras_api_key",
        env_key="CEREBRAS_API_KEY",
        reasoning="none",
        models=(_m("llama-3.3-70b", "Llama 3.3 70B"),),
    ),
    ProviderSpec(
        id="together",
        name="Together",
        base_url="https://api.together.ai/v1",
        env_attr="together_api_key",
        env_key="TOGETHER_API_KEY",
        reasoning="none",
        models=(_m("meta-llama/Llama-3.3-70B-Instruct-Turbo", "Llama 3.3 70B"),),
    ),
    ProviderSpec(
        id="fireworks",
        name="Fireworks",
        base_url="https://api.fireworks.ai/inference/v1",
        env_attr="fireworks_api_key",
        env_key="FIREWORKS_API_KEY",
        reasoning="none",
        models=(_m("accounts/fireworks/models/llama-v3p3-70b-instruct", "Llama 3.3 70B"),),
    ),
    ProviderSpec(
        id="custom",
        name="自定义",
        base_url="",
        env_attr="",
        env_key="",
        reasoning="auto",
        models=(),
    ),
)

_BY_ID = {item.id: item for item in PROVIDERS}
MODEL_CATALOG: list[ModelInfo] = list(_BY_ID["dashscope"].models)


def get_provider(provider_id: str) -> ProviderSpec | None:
    return _BY_ID.get(provider_id)


def known_provider(provider_id: str) -> bool:
    return provider_id in _BY_ID


def find_model(provider_id: str, model_id: str) -> ModelInfo | None:
    spec = get_provider(provider_id)
    if spec is None:
        return None
    return next((model for model in spec.models if model.id == model_id), None)


def get_model_info(model_id: str) -> ModelInfo | None:
    for spec in PROVIDERS:
        for model in spec.models:
            if model.id == model_id and model.input_price is not None:
                return model
    return None


def estimate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float | None:
    info = get_model_info(model_id)
    if info is None or info.input_price is None or info.output_price is None:
        return None
    return (input_tokens * info.input_price + output_tokens * info.output_price) / 1_000_000


def _openai_reasoning_model(model_id: str) -> bool:
    name = model_id.lower()
    return name.startswith(("o1", "o3", "o4")) or "gpt-5" in name


def reasoning_style(provider: str, base_url: str = "", model_id: str = "") -> ReasoningStyle:
    spec = get_provider(provider)
    if spec is None or spec.reasoning == "auto":
        host = base_url.lower()
        if "deepseek.com" in host:
            return "deepseek"
        if "api.openai.com" in host and _openai_reasoning_model(model_id):
            return "openai"
        if not host or "dashscope" in host:
            return "dashscope"
        return "none"
    if spec.reasoning == "openai" and not _openai_reasoning_model(model_id):
        return "none"
    return spec.reasoning


def reasoning_params(
    model_id: str,
    effort: str,
    provider: str = "dashscope",
    base_url: str = "",
) -> dict[str, Any]:
    """把统一思考档位映射成该供应商认识的参数。不认识的供应商不附加参数。"""
    style = reasoning_style(provider, base_url, model_id)
    if style == "dashscope":
        if effort == "off":
            return {"enable_thinking": False}
        if model_id.startswith("qwen"):
            level = {"low": "low", "medium": "medium", "high": "xhigh", "max": "xhigh"}[effort]
        else:
            level = {"low": "low", "medium": "high", "high": "high", "max": "max"}[effort]
        return {"enable_thinking": True, "reasoning_effort": level}
    if style == "deepseek":
        if effort == "off":
            return {"thinking": {"type": "disabled"}}
        level = {"low": "low", "medium": "high", "high": "high", "max": "max"}[effort]
        return {"thinking": {"type": "enabled"}, "reasoning_effort": level}
    if style == "openai":
        level = {
            "off": "low",
            "low": "low",
            "medium": "medium",
            "high": "high",
            "max": "high",
        }[effort]
        return {"reasoning_effort": level}
    return {}


def resolve_credentials(*, provider: str, api_base: str, api_key: str) -> tuple[str, str]:
    """页面上的密钥和地址优先；留空时用该供应商的默认地址和环境变量。"""
    env = get_settings()
    spec = get_provider(provider)
    base = api_base or (spec.base_url if spec else "")
    key = api_key
    if not key and spec and spec.env_attr:
        key = getattr(env, spec.env_attr, "") or ""
    if provider in ("custom", "dashscope", ""):
        if not base:
            base = env.dashscope_base_url
        if not key:
            key = env.dashscope_api_key
    return key, base


def provider_payload() -> list[dict[str, Any]]:
    env = get_settings()
    rows: list[dict[str, Any]] = []
    for spec in PROVIDERS:
        env_set = bool(spec.env_attr and getattr(env, spec.env_attr, ""))
        rows.append(
            {
                "id": spec.id,
                "name": spec.name,
                "base_url": spec.base_url,
                "env_key": spec.env_key,
                "env_key_set": env_set,
                "models": [
                    {
                        "id": model.id,
                        "label": model.label,
                        "description": model.description,
                        "tools": model.tools,
                        "image": model.image,
                    }
                    for model in spec.models
                ],
            }
        )
    return rows
