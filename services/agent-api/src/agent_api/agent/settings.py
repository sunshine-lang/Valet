from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from agent_api.config import get_settings
from agent_api.llm.providers import find_model
from agent_api.tools.files import FILE_TOOLS
from agent_api.tools.live import LIVE_TOOLS
from agent_api.tools.probes import UTILITY_TOOLS
from agent_api.tools.skills import SKILL_TOOLS


def default_system_prompt(name: str) -> str:
    return f"""你是「{name}」，一个用于验证智能体主循环的调试助手。

规则：
- 需要事实或计算时调用工具，不要编造工具结果。
- 工具返回错误时，先根据错误信息修正参数再试；仍然失败就如实告诉用户。
- 需要用户确认的工具，在拿到执行结果之前，不要声称操作已经完成；用户拒绝后不要重复发起。
- 回答简洁，使用中文。
- 若开启思考，思考过程也使用简体中文。"""


def normalize_api_base(value: str) -> str:
    """兼容两种写法：.../v1 或 .../v1/chat/completions。"""
    text = value.strip().rstrip("/")
    suffix = "/chat/completions"
    if text.endswith(suffix):
        text = text[: -len(suffix)].rstrip("/")
    return text


class AgentSettings(BaseModel):
    provider: str = "dashscope"
    api_base: str = Field("", max_length=500)
    api_key: str = Field("", max_length=500)
    model: str = Field(
        default_factory=lambda: get_settings().dashscope_model,
        min_length=1,
        max_length=128,
        description="模型 ID",
    )
    tool_calling: bool = True
    image_input: bool = False
    thinking: bool = True
    thinking_effort: Literal["off", "low", "medium", "high", "max"] = "high"

    @model_validator(mode="before")
    @classmethod
    def default_effort_from_thinking_flag(cls, data: Any) -> Any:
        if (
            isinstance(data, dict)
            and "thinking_effort" not in data
            and data.get("thinking") is False
        ):
            return {**data, "thinking_effort": "off"}
        return data

    @model_validator(mode="after")
    def sync_thinking_flag(self) -> "AgentSettings":
        self.thinking = self.thinking_effort != "off"
        return self

    @model_validator(mode="after")
    def apply_catalog_capabilities(self) -> "AgentSettings":
        """目录中的模型自己声明能不能调工具、能不能看图。自定义或目录外的模型才用手动开关。"""
        if self.provider == "custom":
            return self
        model = find_model(self.provider, self.model)
        if model is None:
            return self
        self.tool_calling = model.tools
        self.image_input = model.image
        self.custom_protocol = False
        return self

    custom_protocol: bool = False
    max_input_tokens: int | None = Field(None, ge=1, le=2_000_000)
    max_output_tokens: int | None = Field(None, ge=1, le=2_000_000)

    @field_validator("provider")
    @classmethod
    def known_provider(cls, value: str) -> str:
        from agent_api.llm.providers import known_provider as is_known

        provider_id = value.strip() or "dashscope"
        if not is_known(provider_id):
            raise ValueError("未知的模型供应商")
        return provider_id

    @field_validator("model")
    @classmethod
    def strip_model(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("请填写模型名称")
        return stripped

    @field_validator("api_base")
    @classmethod
    def strip_api_base(cls, value: str) -> str:
        return normalize_api_base(value)

    @field_validator("api_key")
    @classmethod
    def strip_api_key(cls, value: str) -> str:
        return value.strip()

    def public_dict(self) -> dict[str, Any]:
        data = self.model_dump()
        key = data.pop("api_key")
        data["api_key_set"] = bool(key)
        return data

    def snapshot_dict(self) -> dict[str, Any]:
        data = self.model_dump()
        data.pop("api_key", None)
        return data

    system_prompt: str = Field(
        default_factory=lambda: default_system_prompt(get_settings().agent_name),
        max_length=8000,
    )
    temperature: float = Field(0.3, ge=0, le=2)
    max_steps: int = Field(8, ge=1, le=20, description="单次运行最多调用模型的次数")
    run_timeout_s: int = Field(
        900, ge=1, le=3600, description="单次运行的时间上限。到点后不再调用工具，用已有结果收尾"
    )
    stream_idle_s: int = Field(
        90, ge=1, le=300, description="模型流空闲多久视为卡住。持续有输出就不会触发"
    )
    max_consecutive_failures: int = Field(3, ge=1, le=10, description="工具连续失败几次后停止")
    enabled_tools: list[str] = Field(
        default_factory=lambda: [
            t.name for t in (*UTILITY_TOOLS, *LIVE_TOOLS, *FILE_TOOLS, *SKILL_TOOLS)
        ]
    )
    # None 表示当前目录里的技能全部可用。设成列表后，只把列出的技能交给模型。
    installed_skills: list[str] | None = None
