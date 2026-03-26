"""Ollama local LLM and Embedding providers (HTTP API, no SDK required)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from quantumrag.core.errors import (
    GenerationError,
    LLMModelNotFoundError,
    LLMProviderError,
)
from quantumrag.core.llm.base import (
    LLMResponse,
    measure_latency,
    with_retry,
)
from quantumrag.core.logging import get_logger

logger = get_logger("quantumrag.llm.ollama")

_DEFAULT_BASE_URL = "http://localhost:11434"


def _get_httpx():
    """Lazy-import httpx."""
    try:
        import httpx
    except ImportError as exc:
        raise GenerationError(
            "httpx package is not installed. Install with: pip install httpx",
            provider="ollama",
        ) from exc
    return httpx


# ---------------------------------------------------------------------------
# LLM Provider
# ---------------------------------------------------------------------------


class OllamaLLMProvider:
    """Ollama local model provider via HTTP API.

    All costs are $0 since Ollama runs locally.
    """

    def __init__(
        self,
        model: str = "llama3.1",
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 120.0,
        max_retries: int = 3,
    ) -> None:
        self._httpx = _get_httpx()
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._client = self._httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._httpx.Timeout(timeout),
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

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
            payload = _build_chat_payload(
                self._model, prompt, system, temperature, max_tokens, stream=False
            )
            resp = await self._post("/api/chat", payload)
            message = resp.get("message", {})
            tokens_in = resp.get("prompt_eval_count", 0)
            tokens_out = resp.get("eval_count", 0)
            return LLMResponse(
                text=message.get("content", ""),
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                estimated_cost=0.0,
                model=self._model,
                latency_ms=elapsed(),
            )

        result = await with_retry(
            _call,
            max_retries=self._max_retries,
            provider_name="ollama",
        )
        return result  # type: ignore[return-value]

    # -- generate_stream ---------------------------------------------------

    async def generate_stream(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        payload = _build_chat_payload(
            self._model, prompt, system, temperature, max_tokens, stream=True
        )
        try:
            async with self._client.stream("POST", "/api/chat", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    message = data.get("message", {})
                    content = message.get("content", "")
                    if content:
                        yield content
                    if data.get("done", False):
                        break
        except self._httpx.ConnectError as exc:
            raise LLMProviderError(
                "ollama",
                exc,
                suggestion="Is Ollama running? Start it with: ollama serve",
            ) from exc

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
        json_instruction = (
            "You must respond with ONLY valid JSON. No markdown, no explanation, "
            "no code fences. Output raw JSON only."
        )
        if schema:
            json_instruction += f"\n\nThe JSON must conform to this schema:\n{json.dumps(schema)}"

        combined_system = f"{system}\n\n{json_instruction}" if system else json_instruction

        elapsed = measure_latency()

        async def _call() -> dict:
            payload = _build_chat_payload(
                self._model, prompt, combined_system, temperature, max_tokens, stream=False
            )
            # Ollama supports JSON mode via format param
            payload["format"] = "json"
            resp = await self._post("/api/chat", payload)
            text = resp.get("message", {}).get("content", "{}").strip()
            try:
                return json.loads(text)  # type: ignore[return-value]
            except json.JSONDecodeError as exc_inner:
                raise GenerationError(
                    f"[ollama/{self._model}] Returned invalid JSON: {text[:200]}",
                    provider="ollama",
                ) from exc_inner

        result = await with_retry(
            _call,
            max_retries=self._max_retries,
            provider_name="ollama",
        )
        logger.debug("structured_generation", model=self._model, latency_ms=elapsed())
        return result  # type: ignore[return-value]

    # -- utility -----------------------------------------------------------

    async def list_models(self) -> list[dict[str, Any]]:
        """Query available local models."""
        resp = await self._client.get("/api/tags")
        resp.raise_for_status()
        data = resp.json()
        return data.get("models", [])  # type: ignore[no-any-return]

    # -- internal ----------------------------------------------------------

    async def _post(self, path: str, payload: dict) -> dict:
        try:
            resp = await self._client.post(path, json=payload)
            if resp.status_code == 404:
                raise LLMModelNotFoundError(
                    "ollama",
                    model=self._model,
                    suggestion=f"Model '{self._model}' not found. Pull it with: ollama pull {self._model}",
                )
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]
        except (LLMModelNotFoundError, LLMProviderError):
            raise
        except self._httpx.ConnectError as exc:
            raise LLMProviderError(
                "ollama",
                exc,
                suggestion="Is Ollama running? Start it with: ollama serve",
            ) from exc


# ---------------------------------------------------------------------------
# Embedding Provider
# ---------------------------------------------------------------------------


class OllamaEmbeddingProvider:
    """Ollama local embedding provider."""

    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str = _DEFAULT_BASE_URL,
        dimensions: int = 768,
        timeout: float = 120.0,
    ) -> None:
        self._httpx = _get_httpx()
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._dimensions = dimensions
        self._client = self._httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._httpx.Timeout(timeout),
        )

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        try:
            resp = await self._client.post(
                "/api/embed",
                json={"model": self._model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("embeddings", [])  # type: ignore[no-any-return]
        except self._httpx.ConnectError as exc:
            raise LLMProviderError(
                "ollama",
                exc,
                suggestion="Is Ollama running? Start it with: ollama serve",
            ) from exc

    async def embed_query(self, query: str) -> list[float]:
        results = await self.embed([query])
        return results[0]

    async def close(self) -> None:
        await self._client.aclose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_chat_payload(
    model: str,
    prompt: str,
    system: str | None,
    temperature: float,
    max_tokens: int,
    *,
    stream: bool,
) -> dict[str, Any]:
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return {
        "model": model,
        "messages": messages,
        "stream": stream,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
