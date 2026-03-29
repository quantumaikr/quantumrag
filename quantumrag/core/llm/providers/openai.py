"""OpenAI LLM and Embedding providers."""

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

logger = get_logger("quantumrag.llm.openai")

# ---------------------------------------------------------------------------
# Pricing per 1M tokens (USD) – updated 2025-Q1
# ---------------------------------------------------------------------------

_PRICING: dict[str, tuple[float, float]] = {
    # (input_per_1M, output_per_1M)
    "gpt-5.4-nano": (0.10, 0.40),
    "gpt-5.4-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}

_EMBEDDING_PRICING: dict[str, float] = {
    # price per 1M tokens
    "text-embedding-3-small": 0.02,
    "text-embedding-3-large": 0.13,
    "text-embedding-ada-002": 0.10,
}

# Max texts per single embeddings API call
_EMBEDDING_BATCH_SIZE = 2048


def _get_openai() -> Any:
    """Lazy-import the openai SDK."""
    try:
        import openai
    except ImportError as exc:
        raise GenerationError(
            "openai package is not installed. Install with: pip install 'quantumrag[all]'",
            provider="openai",
        ) from exc
    return openai


def _convert_openai_error(exc: Exception) -> Exception:
    """Convert an openai SDK exception to a standardized QuantumRAG error."""
    try:
        openai = _get_openai()
    except GenerationError:
        return exc  # SDK not available, return original error unchanged

    if isinstance(exc, openai.AuthenticationError):
        return LLMAuthenticationError("openai")
    if isinstance(exc, openai.RateLimitError):
        retry_after = getattr(exc, "headers", {})
        retry_secs: float | None = None
        if hasattr(retry_after, "get"):
            raw = retry_after.get("retry-after")
            if raw is not None:
                with contextlib.suppress(ValueError, TypeError):
                    retry_secs = float(raw)
        return LLMRateLimitError("openai", retry_after_seconds=retry_secs)
    if isinstance(exc, openai.NotFoundError):
        return LLMModelNotFoundError("openai", model=str(getattr(exc, "param", "") or "unknown"))
    if isinstance(exc, openai.BadRequestError):
        msg = str(exc).lower()
        if "context length" in msg or "maximum context" in msg or "too many tokens" in msg:
            return LLMContextLengthError("openai")
        return LLMProviderError("openai", exc)
    if isinstance(exc, openai.APIError):
        return LLMProviderError("openai", exc)
    return exc


# ---------------------------------------------------------------------------
# LLM Provider
# ---------------------------------------------------------------------------


class OpenAILLMProvider:
    """OpenAI chat-completion provider.

    Supports gpt-5.4-nano, gpt-5.4-mini, gpt-4.1-nano, gpt-4.1-mini, gpt-4.1, gpt-4o-mini, gpt-4o.
    """

    # Models that require max_completion_tokens instead of max_tokens
    _MAX_COMPLETION_TOKENS_MODELS = {"gpt-5.4-nano", "gpt-5.4-mini", "gpt-5.4"}

    def __init__(
        self,
        model: str = "gpt-5.4-nano",
        api_key: str | None = None,
        base_url: str | None = None,
        max_retries: int = 5,
    ) -> None:
        openai = _get_openai()

        kwargs: dict[str, Any] = {}
        if api_key is not None:
            kwargs["api_key"] = api_key
        if base_url is not None:
            kwargs["base_url"] = base_url

        self._client = openai.AsyncOpenAI(**kwargs)
        self._model = model
        self._max_retries = max_retries
        self._use_max_completion_tokens = model in self._MAX_COMPLETION_TOKENS_MODELS

    def _token_limit_kwarg(self, max_tokens: int) -> dict[str, int]:
        """Return the correct token limit parameter for the model."""
        if self._use_max_completion_tokens:
            return {"max_completion_tokens": max_tokens}
        return {"max_tokens": max_tokens}

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
            messages = _build_messages(prompt, system)
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                **self._token_limit_kwarg(max_tokens),
            )
            choice = resp.choices[0]
            usage = resp.usage
            tokens_in = usage.prompt_tokens if usage else 0
            tokens_out = usage.completion_tokens if usage else 0
            price_in, price_out = _PRICING.get(self._model, (0.0, 0.0))
            return LLMResponse(
                text=choice.message.content or "",
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
                provider_name="openai",
            )
            return result  # type: ignore[return-value]
        except GenerationError as exc:
            orig = exc.__cause__
            if orig is not None and isinstance(orig, Exception):
                converted = _convert_openai_error(orig)
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
        messages = _build_messages(prompt, system)
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            **self._token_limit_kwarg(max_tokens),
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    # -- generate_structured -----------------------------------------------

    async def generate_structured(
        self,
        prompt: str,
        *,
        schema: dict | None = None,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> dict:
        elapsed = measure_latency()

        async def _call() -> dict:
            messages = _build_messages(prompt, system)
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                **self._token_limit_kwarg(max_tokens),
                response_format={"type": "json_object"},
            )
            text = resp.choices[0].message.content or "{}"
            try:
                return json.loads(text)  # type: ignore[return-value]
            except json.JSONDecodeError as exc:
                raise GenerationError(
                    f"[openai/{self._model}] Returned invalid JSON: {text[:200]}",
                    provider="openai",
                ) from exc

        try:
            result = await with_retry(
                _call,
                max_retries=self._max_retries,
                provider_name="openai",
            )
            logger.debug("structured_generation", model=self._model, latency_ms=elapsed())
            return result  # type: ignore[return-value]
        except GenerationError as exc:
            orig = exc.__cause__
            if orig is not None and isinstance(orig, Exception):
                converted = _convert_openai_error(orig)
                if converted is not orig:
                    raise converted from orig
            raise


# ---------------------------------------------------------------------------
# Embedding Provider
# ---------------------------------------------------------------------------


class OpenAIEmbeddingProvider:
    """OpenAI embedding provider with automatic batch splitting."""

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: str | None = None,
        base_url: str | None = None,
        dimensions: int | None = None,
    ) -> None:
        openai = _get_openai()

        kwargs: dict[str, Any] = {}
        if api_key is not None:
            kwargs["api_key"] = api_key
        if base_url is not None:
            kwargs["base_url"] = base_url

        self._client = openai.AsyncOpenAI(**kwargs)
        self._model = model
        # text-embedding-3-small default 1536, text-embedding-3-large default 3072
        self._dimensions = dimensions or (3072 if "large" in model else 1536)

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts, automatically batching with retry."""
        if not texts:
            return []

        import asyncio as _aio

        all_embeddings: list[list[float]] = []
        for batch_start in range(0, len(texts), _EMBEDDING_BATCH_SIZE):
            batch = texts[batch_start : batch_start + _EMBEDDING_BATCH_SIZE]
            # Retry with exponential backoff for rate limits
            for attempt in range(5):
                try:
                    resp = await self._client.embeddings.create(
                        model=self._model,
                        input=batch,
                        dimensions=self._dimensions,
                    )
                    sorted_data = sorted(resp.data, key=lambda d: d.index)
                    all_embeddings.extend([d.embedding for d in sorted_data])
                    break
                except Exception as e:
                    if "rate" in str(e).lower() or "429" in str(e):
                        delay = 2**attempt
                        logger.warning("embedding_rate_limited", attempt=attempt, delay=delay)
                        await _aio.sleep(delay)
                    else:
                        raise

        return all_embeddings

    async def embed_query(self, query: str) -> list[float]:
        """Embed a single query string."""
        results = await self.embed([query])
        return results[0]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_messages(
    prompt: str,
    system: str | None,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return messages
