"""Anthropic (Claude) LLM provider."""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator
from typing import Any

from quantumrag.core.errors import (
    GenerationError,
    LLMAuthenticationError,
    LLMContextLengthError,
    LLMModelNotFoundError,
    LLMProviderError,
    LLMRateLimitError,
)
from quantumrag.core.llm.base import (
    LLMResponse,
    estimate_cost,
    measure_latency,
    with_retry,
)
from quantumrag.core.logging import get_logger

logger = get_logger("quantumrag.llm.anthropic")

# ---------------------------------------------------------------------------
# Pricing per 1M tokens (USD) – updated 2025-Q1
# ---------------------------------------------------------------------------

_PRICING: dict[str, tuple[float, float]] = {
    # (input_per_1M, output_per_1M)
    "claude-haiku-4.5": (0.80, 4.00),
    "claude-haiku-4.5-20250415": (0.80, 4.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-opus-4": (15.00, 75.00),
    "claude-opus-4-20250514": (15.00, 75.00),
}

# Models that support prompt caching
_CACHE_SUPPORTED_MODELS = {
    "claude-haiku-4.5",
    "claude-haiku-4.5-20250415",
    "claude-sonnet-4",
    "claude-sonnet-4-20250514",
    "claude-opus-4",
    "claude-opus-4-20250514",
}


def _get_anthropic() -> Any:
    """Lazy-import the anthropic SDK."""
    try:
        import anthropic
    except ImportError as exc:
        raise GenerationError(
            "anthropic package is not installed. Install with: pip install 'quantumrag[all]'",
            provider="anthropic",
        ) from exc
    return anthropic


def _convert_anthropic_error(exc: Exception) -> Exception:
    """Convert an anthropic SDK exception to a standardized QuantumRAG error."""
    anthropic = _get_anthropic()

    if isinstance(exc, anthropic.AuthenticationError):
        return LLMAuthenticationError("anthropic")
    if isinstance(exc, anthropic.RateLimitError):
        retry_after: float | None = None
        headers = getattr(exc, "response", None)
        if headers is not None:
            raw = getattr(headers, "headers", {}).get("retry-after")
            if raw is not None:
                with contextlib.suppress(ValueError, TypeError):
                    retry_after = float(raw)
        return LLMRateLimitError("anthropic", retry_after_seconds=retry_after)
    if isinstance(exc, anthropic.NotFoundError):
        return LLMModelNotFoundError("anthropic", model="unknown")
    if isinstance(exc, anthropic.BadRequestError):
        msg = str(exc).lower()
        if "context length" in msg or "too many tokens" in msg or "max tokens" in msg:
            return LLMContextLengthError("anthropic")
        return LLMProviderError("anthropic", exc)
    if isinstance(exc, anthropic.APIError):
        return LLMProviderError("anthropic", exc)
    return exc


# ---------------------------------------------------------------------------
# LLM Provider
# ---------------------------------------------------------------------------


class AnthropicLLMProvider:
    """Anthropic Claude provider.

    Supports claude-haiku-4.5, claude-sonnet-4, claude-opus-4 (and dated variants).
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,
        max_retries: int = 3,
        enable_cache: bool = True,
    ) -> None:
        anthropic = _get_anthropic()

        kwargs: dict[str, Any] = {}
        if api_key is not None:
            kwargs["api_key"] = api_key

        self._client = anthropic.AsyncAnthropic(**kwargs)
        self._model = model
        self._max_retries = max_retries
        self._enable_cache = enable_cache and model in _CACHE_SUPPORTED_MODELS

    # -- generate ----------------------------------------------------------

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        elapsed = measure_latency()

        async def _call() -> LLMResponse:
            kwargs = self._build_kwargs(prompt, system, temperature, max_tokens)
            resp = await self._client.messages.create(**kwargs)
            tokens_in = resp.usage.input_tokens
            tokens_out = resp.usage.output_tokens
            price_in, price_out = _PRICING.get(self._model, (0.0, 0.0))
            text = _extract_text(resp)
            return LLMResponse(
                text=text,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                estimated_cost=estimate_cost(tokens_in, tokens_out, price_in, price_out),
                model=self._model,
                latency_ms=elapsed(),
            )

        try:
            result = await with_retry(
                _call,
                max_retries=self._max_retries,
                provider_name="anthropic",
            )
            return result  # type: ignore[return-value]
        except GenerationError as exc:
            orig = exc.__cause__
            if orig is not None and isinstance(orig, Exception):
                converted = _convert_anthropic_error(orig)
                if converted is not orig:
                    raise converted from orig
            raise

    # -- generate_stream ---------------------------------------------------

    async def generate_stream(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        kwargs = self._build_kwargs(prompt, system, temperature, max_tokens)
        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    # -- generate_structured -----------------------------------------------

    async def generate_structured(
        self,
        prompt: str,
        *,
        schema: dict[str, Any] | None = None,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        # Anthropic doesn't have a native JSON mode; we instruct in the system prompt.
        json_instruction = (
            "You must respond with ONLY valid JSON. No markdown, no explanation, "
            "no code fences. Output raw JSON only."
        )
        if schema:
            json_instruction += f"\n\nThe JSON must conform to this schema:\n{json.dumps(schema)}"

        combined_system = f"{system}\n\n{json_instruction}" if system else json_instruction

        elapsed = measure_latency()

        async def _call() -> dict[str, Any]:
            kwargs = self._build_kwargs(prompt, combined_system, temperature, max_tokens)
            resp = await self._client.messages.create(**kwargs)
            text = _extract_text(resp).strip()
            # Strip potential markdown code fences
            if text.startswith("```"):
                text = text.split("\n", 1)[-1]
            if text.endswith("```"):
                text = text.rsplit("```", 1)[0]
            text = text.strip()
            try:
                return json.loads(text)  # type: ignore[no-any-return]
            except json.JSONDecodeError as exc:
                raise GenerationError(
                    f"[anthropic/{self._model}] Returned invalid JSON: {text[:200]}",
                    provider="anthropic",
                ) from exc

        try:
            result = await with_retry(
                _call,
                max_retries=self._max_retries,
                provider_name="anthropic",
            )
            logger.debug("structured_generation", model=self._model, latency_ms=elapsed())
            return result  # type: ignore[return-value]
        except GenerationError as exc:
            orig = exc.__cause__
            if orig is not None and isinstance(orig, Exception):
                converted = _convert_anthropic_error(orig)
                if converted is not orig:
                    raise converted from orig
            raise

    # -- internals ---------------------------------------------------------

    def _build_kwargs(
        self,
        prompt: str,
        system: str | None,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if system:
            if self._enable_cache:
                # Use cache_control for system prompt caching
                kwargs["system"] = [
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            else:
                kwargs["system"] = system

        return kwargs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_text(resp: Any) -> str:
    """Extract concatenated text from an Anthropic message response."""
    parts: list[str] = []
    for block in resp.content:
        if hasattr(block, "text"):
            parts.append(block.text)
    return "".join(parts)
