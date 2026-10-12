from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx
from openai import AsyncOpenAI

from agent_api.llm.base import LLMRequest, LLMResult, TextDelta, ThinkingDelta, ToolCall
from agent_api.llm.catalog import reasoning_params


@dataclass
class _PartialToolCall:
    id: str = ""
    name: str = ""
    arguments: list[str] = field(default_factory=list)


class OpenAICompatClient:
    """任意兼容 OpenAI Chat Completions 的服务（百炼、DeepSeek、vLLM 等）。"""

    priced = True

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        provider: str,
        timeout_s: float = 300.0,
        extra_body: dict | None = None,
    ) -> None:
        self.provider = provider
        self._api_key = api_key
        self._base_url = base_url
        # 读超时只兜住「一块数据都等不到」。真正的空闲判断在主循环里，有输出就会重置。
        self._timeout = httpx.Timeout(connect=30.0, read=timeout_s, write=30.0, pool=30.0)
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=self._timeout)
        self._extra_body = extra_body or {}

    def _client_for(self, request: LLMRequest) -> AsyncOpenAI:
        key = self._api_key if request.api_key is None else request.api_key
        base = self._base_url if request.base_url is None else request.base_url
        if key == self._api_key and base == self._base_url:
            return self._client
        return AsyncOpenAI(api_key=key or "missing", base_url=base, timeout=self._timeout)

    async def stream(
        self, request: LLMRequest
    ) -> AsyncIterator[TextDelta | ThinkingDelta | LLMResult]:
        kwargs: dict = {}
        if request.tools:
            kwargs["tools"] = request.tools
            if not request.custom_protocol:
                kwargs["parallel_tool_calls"] = True
        if request.max_tokens:
            kwargs["max_tokens"] = request.max_tokens
        extra_body: dict = {}
        if not request.custom_protocol:
            extra_body = {
                **self._extra_body,
                **reasoning_params(
                    request.model,
                    request.thinking_effort,
                    request.provider,
                    request.base_url or "",
                ),
            }
        if extra_body:
            kwargs["extra_body"] = extra_body

        stream = await self._client_for(request).chat.completions.create(
            model=request.model,
            messages=request.messages,
            temperature=request.temperature,
            stream=True,
            stream_options={"include_usage": True},
            **kwargs,
        )

        result = LLMResult()
        content: list[str] = []
        reasoning: list[str] = []
        partials: dict[int, _PartialToolCall] = {}

        async for chunk in stream:
            if chunk.model:
                result.response_model = chunk.model
            if chunk.usage:
                result.input_tokens = chunk.usage.prompt_tokens or 0
                result.output_tokens = chunk.usage.completion_tokens or 0
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            thought = getattr(delta, "reasoning_content", None)
            if thought:
                reasoning.append(thought)
                yield ThinkingDelta(thought)
            if delta.content:
                content.append(delta.content)
                yield TextDelta(delta.content)
            for tc in delta.tool_calls or []:
                partial = partials.setdefault(tc.index, _PartialToolCall())
                if tc.id:
                    partial.id = tc.id
                if tc.function and tc.function.name:
                    partial.name = tc.function.name
                if tc.function and tc.function.arguments:
                    partial.arguments.append(tc.function.arguments)
            if choice.finish_reason:
                result.finish_reason = choice.finish_reason

        result.content = "".join(content)
        result.reasoning = "".join(reasoning)
        result.tool_calls = [
            ToolCall(id=p.id or f"call_{i}", name=p.name, arguments="".join(p.arguments) or "{}")
            for i, p in sorted(partials.items())
        ]
        yield result
