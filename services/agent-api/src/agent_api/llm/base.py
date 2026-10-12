from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # 模型给出的原始 JSON 字符串，校验在工具层做

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "name": self.name, "arguments": self.arguments}


@dataclass
class LLMRequest:
    model: str
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    temperature: float
    api_key: str | None = None
    base_url: str | None = None
    provider: str = "dashscope"
    max_tokens: int | None = None
    thinking_effort: str = "high"
    # 自定义接口不附加思考参数，也不强制 parallel_tool_calls
    custom_protocol: bool = False


@dataclass
class TextDelta:
    text: str


@dataclass
class ThinkingDelta:
    text: str


@dataclass
class LLMResult:
    content: str = ""
    reasoning: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    response_model: str | None = None


class LLMClient(Protocol):
    provider: str
    # False 表示不产生真实费用（如本地模拟模型），追踪里的费用记为 0
    priced: bool

    def stream(self, request: LLMRequest) -> AsyncIterator[TextDelta | ThinkingDelta | LLMResult]:
        """流式产出思考增量和文本增量，最后产出且仅产出一个 LLMResult。"""
        ...
