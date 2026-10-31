"""Provider adapters. This is the only module that imports a provider SDK (ADR-003).

History is kept in each provider's native message format, so a session stays with its provider
and Claude's content blocks, including thinking blocks, are replayed unchanged.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Protocol

from .config import ANTHROPIC, ConfigError, Settings

logger = logging.getLogger(__name__)

MAX_OUTPUT_TOKENS = 16000
REQUEST_TIMEOUT_SECONDS = 90.0
ANTHROPIC_BASE_URL = "https://api.anthropic.com"
REFUSAL_FALLBACK_BETA = "server-side-fallback-2026-07-01"
REFUSAL_FALLBACK_MODELS = ("claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5")


class LLMUnavailable(Exception):
    """The language service failed after the SDK's own retries."""


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class ToolResult:
    call: ToolCall
    content: str
    is_error: bool = False


@dataclass
class LLMTurn:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    assistant_message: dict = field(default_factory=dict)
    refused: bool = False
    input_tokens: int = 0
    output_tokens: int = 0


class LLMClient(Protocol):
    provider: str
    model: str

    def complete(self, system: str, messages: list[dict], tools: list[dict]) -> LLMTurn: ...
    def user_message(self, text: str) -> dict: ...
    def assistant_text_message(self, text: str) -> dict: ...
    def tool_result_messages(self, results: list[ToolResult]) -> list[dict]: ...


class AnthropicLLM:
    provider = ANTHROPIC

    def __init__(self, settings: Settings, client=None) -> None:
        import anthropic

        self._errors = anthropic
        self.model = settings.model
        self._effort = settings.effort
        # The base URL is explicit so an ANTHROPIC_BASE_URL left in the shell can't redirect the app.
        self._client = client or anthropic.Anthropic(
            api_key=settings.api_key,
            base_url=settings.base_url or ANTHROPIC_BASE_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

    def complete(self, system: str, messages: list[dict], tools: list[dict]) -> LLMTurn:
        request = dict(
            model=self.model,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            tools=[
                {"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
                for t in tools
            ],
            messages=messages,
            output_config={"effort": self._effort},
        )
        try:
            if self.model in REFUSAL_FALLBACK_MODELS:
                response = self._client.beta.messages.create(
                    betas=[REFUSAL_FALLBACK_BETA], fallbacks="default", **request
                )
            else:
                response = self._client.messages.create(**request)
        except self._errors.RateLimitError as error:
            logger.warning("Rate limited by the language service: %s", error)
            raise LLMUnavailable("rate_limited") from error
        except self._errors.APIStatusError as error:
            logger.error("Language service returned %s: %s", error.status_code, error.message)
            raise LLMUnavailable(f"status_{error.status_code}") from error
        except self._errors.APIConnectionError as error:
            logger.error("Could not reach the language service: %s", error)
            raise LLMUnavailable("connection") from error

        content = [block.model_dump(mode="json", exclude_none=True) for block in response.content]
        return LLMTurn(
            text="".join(b.text for b in response.content if b.type == "text"),
            tool_calls=[
                ToolCall(id=b.id, name=b.name, arguments=dict(b.input))
                for b in response.content
                if b.type == "tool_use"
            ],
            assistant_message={"role": "assistant", "content": content},
            refused=response.stop_reason == "refusal",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    def user_message(self, text: str) -> dict:
        return {"role": "user", "content": text}

    def assistant_text_message(self, text: str) -> dict:
        return {"role": "assistant", "content": text}

    def tool_result_messages(self, results: list[ToolResult]) -> list[dict]:
        blocks = [
            {"type": "tool_result", "tool_use_id": r.call.id, "content": r.content, "is_error": r.is_error}
            for r in results
        ]
        return [{"role": "user", "content": blocks}]


class OpenAICompatibleLLM:
    """Any endpoint that speaks the Chat Completions format: Gemini, Groq, Ollama and others."""

    provider = "openai_compatible"

    def __init__(self, settings: Settings, client=None) -> None:
        import openai

        self._errors = openai
        self.model = settings.model
        self._client = client or openai.OpenAI(
            api_key=settings.api_key or "not-needed",
            base_url=settings.base_url,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

    def complete(self, system: str, messages: list[dict], tools: list[dict]) -> LLMTurn:
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, *messages],
                tools=[
                    {
                        "type": "function",
                        "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]},
                    }
                    for t in tools
                ],
            )
        except self._errors.RateLimitError as error:
            logger.warning("Rate limited by the language service: %s", error)
            raise LLMUnavailable("rate_limited") from error
        except self._errors.APIStatusError as error:
            logger.error("Language service returned %s: %s", error.status_code, error.message)
            raise LLMUnavailable(f"status_{error.status_code}") from error
        except self._errors.APIConnectionError as error:
            logger.error("Could not reach the language service: %s", error)
            raise LLMUnavailable("connection") from error

        message = response.choices[0].message
        assistant_message = message.model_dump(mode="json", exclude_none=True)
        assistant_message["content"] = message.content or ""
        usage = response.usage
        return LLMTurn(
            text=message.content or "",
            tool_calls=[
                ToolCall(id=c.id, name=c.function.name, arguments=self._parse_arguments(c.function.arguments))
                for c in message.tool_calls or []
            ],
            assistant_message=assistant_message,
            refused=response.choices[0].finish_reason == "content_filter",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )

    @staticmethod
    def _parse_arguments(raw: str | None) -> dict:
        try:
            parsed = json.loads(raw or "{}")
        except json.JSONDecodeError:
            parsed = None
        # Unusable arguments reach the tool as an unknown parameter, which comes back as a tool error.
        return parsed if isinstance(parsed, dict) else {"invalid_arguments": raw}

    def user_message(self, text: str) -> dict:
        return {"role": "user", "content": text}

    def assistant_text_message(self, text: str) -> dict:
        return {"role": "assistant", "content": text}

    def tool_result_messages(self, results: list[ToolResult]) -> list[dict]:
        return [{"role": "tool", "tool_call_id": r.call.id, "content": r.content} for r in results]


def build_llm(settings: Settings) -> LLMClient:
    if settings.provider == ANTHROPIC:
        if not settings.api_key:
            raise ConfigError("Set LLM_API_KEY (or ANTHROPIC_API_KEY) in .env. See .env.example for a free alternative.")
        return AnthropicLLM(settings)
    if not settings.base_url:
        raise ConfigError("LLM_BASE_URL is required with the openai_compatible provider. See .env.example.")
    return OpenAICompatibleLLM(settings)
