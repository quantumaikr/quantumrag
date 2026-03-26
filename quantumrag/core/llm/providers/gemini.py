"""Google Gemini LLM and Embedding providers."""

from __future__ import annotations

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

logger = get_logger("quantumrag.llm.gemini")

# ---------------------------------------------------------------------------
# Pricing per 1M tokens (USD) – updated 2025-Q1
# ---------------------------------------------------------------------------

_PRICING: dict[str, tuple[float, float]] = {
    # (input_per_1M, output_per_1M)
    "gemini-3.1-flash-lite-preview": (0.075, 0.30),
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-2.0-flash-lite": (0.075, 0.30),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
}

_EMBEDDING_PRICING: dict[str, float] = {
    # price per 1M tokens
    "gemini-embedding-001": 0.00,  # free tier available
    "gemini-embedding-2-preview": 0.00,
}

# Max texts per single embeddings API call
_EMBEDDING_BATCH_SIZE = 100


def _get_genai():
    """Lazy-import the google-genai SDK."""
    try:
        from google import genai
    except ImportError as exc:
        raise GenerationError(
            "google-genai package is not installed. "
            "Install with: pip install 'google-genai>=1.0'",
            provider="gemini",
        ) from exc
    return genai


def _convert_gemini_error(exc: Exception) -> Exception:
    """Convert a google-genai SDK exception to a standardized QuantumRAG error.

    Only converts errors that originate from the Gemini API/SDK, not
    QuantumRAG's own errors (e.g. GenerationError from invalid JSON).
    """
    # Don't re-convert our own errors
    if isinstance(exc, (GenerationError, LLMProviderError, LLMAuthenticationError)):
        return exc

    exc_name = type(exc).__name__
    msg = str(exc).lower()

    if "invalid api key" in msg or "api_key_invalid" in msg or "401" in msg:
        return LLMAuthenticationError("gemini")
    if "permission" in msg and "denied" in msg:
        return LLMAuthenticationError("gemini")
    if "quota" in msg or "resource_exhausted" in msg or "429" in msg:
        return LLMRateLimitError("gemini")
    if "rate limit" in msg:
        return LLMRateLimitError("gemini")
    if ("not found" in msg or "404" in msg) and "model" in msg:
        return LLMModelNotFoundError("gemini", model="unknown")
    if "context length" in msg or "too many tokens" in msg or "token limit" in msg:
        return LLMContextLengthError("gemini")
    if exc_name in {"ClientError", "APIError", "ServerError"}:
        return LLMProviderError("gemini", exc)
    return exc


# ---------------------------------------------------------------------------
# LLM Provider
# ---------------------------------------------------------------------------


class GeminiLLMProvider:
    """Google Gemini chat provider.

    Supports gemini-3.1-flash-lite-preview, gemini-2.5-flash, gemini-2.5-pro, etc.
    Uses the new google-genai SDK (unified API).
    """

    def __init__(
        self,
        model: str = "gemini-3.1-flash-lite-preview",
        api_key: str | None = None,
        max_retries: int = 3,
    ) -> None:
        genai = _get_genai()

        kwargs: dict[str, Any] = {}
        if api_key is not None:
            kwargs["api_key"] = api_key

        self._client = genai.Client(**kwargs)
        self._model = model
        self._max_retries = max_retries

    # -- generate ----------------------------------------------------------

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        genai = _get_genai()
        elapsed = measure_latency()

        async def _call() -> LLMResponse:
            config = genai.types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
            if system:
                config.system_instruction = system

            resp = await self._client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=config,
            )
            text = resp.text or ""
            tokens_in = resp.usage_metadata.prompt_token_count if resp.usage_metadata else 0
            tokens_out = (
                resp.usage_metadata.candidates_token_count if resp.usage_metadata else 0
            )
            price_in, price_out = _PRICING.get(self._model, (0.0, 0.0))
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
                provider_name="gemini",
            )
            return result  # type: ignore[return-value]
        except GenerationError as exc:
            orig = exc.__cause__
            if orig is not None:
                converted = _convert_gemini_error(orig)
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
        genai = _get_genai()
        config = genai.types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        if system:
            config.system_instruction = system

        async for chunk in await self._client.aio.models.generate_content_stream(
            model=self._model,
            contents=prompt,
            config=config,
        ):
            if chunk.text:
                yield chunk.text

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
        genai = _get_genai()
        elapsed = measure_latency()

        async def _call() -> dict:
            config = genai.types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
                response_mime_type="application/json",
            )
            if system:
                config.system_instruction = system

            resp = await self._client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=config,
            )
            text = (resp.text or "{}").strip()
            # Strip potential markdown code fences
            if text.startswith("```"):
                text = text.split("\n", 1)[-1]
            if text.endswith("```"):
                text = text.rsplit("```", 1)[0]
            text = text.strip()
            try:
                return json.loads(text)  # type: ignore[return-value]
            except json.JSONDecodeError as exc:
                raise GenerationError(
                    f"[gemini/{self._model}] Returned invalid JSON: {text[:200]}",
                    provider="gemini",
                ) from exc

        try:
            result = await with_retry(
                _call,
                max_retries=self._max_retries,
                provider_name="gemini",
            )
            logger.debug("structured_generation", model=self._model, latency_ms=elapsed())
            return result  # type: ignore[return-value]
        except GenerationError as exc:
            orig = exc.__cause__
            if orig is not None:
                converted = _convert_gemini_error(orig)
                if converted is not orig:
                    raise converted from orig
            raise


# ---------------------------------------------------------------------------
# Embedding Provider
# ---------------------------------------------------------------------------


class GeminiEmbeddingProvider:
    """Google Gemini embedding provider with automatic batch splitting."""

    def __init__(
        self,
        model: str = "gemini-embedding-001",
        api_key: str | None = None,
        dimensions: int | None = None,
    ) -> None:
        genai = _get_genai()

        kwargs: dict[str, Any] = {}
        if api_key is not None:
            kwargs["api_key"] = api_key

        self._client = genai.Client(**kwargs)
        self._model = model
        self._dimensions = dimensions or 3072

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts, automatically batching if needed."""
        if not texts:
            return []

        genai = _get_genai()
        all_embeddings: list[list[float]] = []

        for batch_start in range(0, len(texts), _EMBEDDING_BATCH_SIZE):
            batch = texts[batch_start : batch_start + _EMBEDDING_BATCH_SIZE]
            config = genai.types.EmbedContentConfig(
                output_dimensionality=self._dimensions,
            )
            resp = await self._client.aio.models.embed_content(
                model=self._model,
                contents=batch,
                config=config,
            )
            all_embeddings.extend([e.values for e in resp.embeddings])

        return all_embeddings

    async def embed_query(self, query: str) -> list[float]:
        """Embed a single query string."""
        results = await self.embed([query])
        return results[0]
