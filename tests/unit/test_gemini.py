"""Tests for Google Gemini LLM and Embedding providers."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from quantumrag.core.errors import (
    GenerationError,
    LLMAuthenticationError,
    LLMModelNotFoundError,
    LLMRateLimitError,
)


# ---------------------------------------------------------------------------
# GeminiLLMProvider
# ---------------------------------------------------------------------------


class TestGeminiLLMProvider:
    def _make_provider(self, mock_genai: MagicMock, model: str = "gemini-3.1-flash-lite-preview") -> Any:
        from quantumrag.core.llm.providers.gemini import GeminiLLMProvider

        with patch("quantumrag.core.llm.providers.gemini._get_genai", return_value=mock_genai):
            return GeminiLLMProvider(model=model, api_key="test-key")

    def _mock_genai(self) -> MagicMock:
        mock = MagicMock()
        mock.Client.return_value = MagicMock()
        mock.types.GenerateContentConfig = MagicMock
        return mock

    async def test_generate(self) -> None:
        mock_genai = self._mock_genai()
        provider = self._make_provider(mock_genai)

        usage = SimpleNamespace(prompt_token_count=10, candidates_token_count=20)
        resp = SimpleNamespace(text="Hello from Gemini", usage_metadata=usage)
        provider._client.aio.models.generate_content = AsyncMock(return_value=resp)

        with patch("quantumrag.core.llm.providers.gemini._get_genai", return_value=mock_genai):
            result = await provider.generate("Hi", system="Be helpful")

        assert result.text == "Hello from Gemini"
        assert result.tokens_in == 10
        assert result.tokens_out == 20
        assert result.model == "gemini-3.1-flash-lite-preview"
        assert result.estimated_cost > 0
        assert result.latency_ms > 0

    async def test_generate_no_usage_metadata(self) -> None:
        mock_genai = self._mock_genai()
        provider = self._make_provider(mock_genai)

        resp = SimpleNamespace(text="Response", usage_metadata=None)
        provider._client.aio.models.generate_content = AsyncMock(return_value=resp)

        with patch("quantumrag.core.llm.providers.gemini._get_genai", return_value=mock_genai):
            result = await provider.generate("Hi")

        assert result.text == "Response"
        assert result.tokens_in == 0
        assert result.tokens_out == 0

    async def test_generate_structured(self) -> None:
        mock_genai = self._mock_genai()
        provider = self._make_provider(mock_genai)

        usage = SimpleNamespace(prompt_token_count=15, candidates_token_count=25)
        resp = SimpleNamespace(text='{"answer": "yes"}', usage_metadata=usage)
        provider._client.aio.models.generate_content = AsyncMock(return_value=resp)

        with patch("quantumrag.core.llm.providers.gemini._get_genai", return_value=mock_genai):
            result = await provider.generate_structured("Is the sky blue?")

        assert result == {"answer": "yes"}

    async def test_generate_structured_invalid_json(self) -> None:
        mock_genai = self._mock_genai()
        provider = self._make_provider(mock_genai)

        usage = SimpleNamespace(prompt_token_count=5, candidates_token_count=5)
        resp = SimpleNamespace(text="not json at all", usage_metadata=usage)
        provider._client.aio.models.generate_content = AsyncMock(return_value=resp)

        with patch("quantumrag.core.llm.providers.gemini._get_genai", return_value=mock_genai):
            with pytest.raises(GenerationError, match=r"\[gemini/gemini-3\.1-flash-lite-preview\].*invalid JSON"):
                await provider.generate_structured("test")

    async def test_generate_structured_strips_code_fences(self) -> None:
        mock_genai = self._mock_genai()
        provider = self._make_provider(mock_genai)

        usage = SimpleNamespace(prompt_token_count=5, candidates_token_count=5)
        resp = SimpleNamespace(text='```json\n{"key": "value"}\n```', usage_metadata=usage)
        provider._client.aio.models.generate_content = AsyncMock(return_value=resp)

        with patch("quantumrag.core.llm.providers.gemini._get_genai", return_value=mock_genai):
            result = await provider.generate_structured("test")

        assert result == {"key": "value"}

    async def test_missing_sdk(self) -> None:
        with (
            patch(
                "quantumrag.core.llm.providers.gemini._get_genai",
                side_effect=GenerationError("google-genai package is not installed", provider="gemini"),
            ),
            pytest.raises(GenerationError, match="not installed"),
        ):
            from quantumrag.core.llm.providers.gemini import GeminiLLMProvider

            GeminiLLMProvider(api_key="x")


# ---------------------------------------------------------------------------
# GeminiEmbeddingProvider
# ---------------------------------------------------------------------------


class TestGeminiEmbeddingProvider:
    def _make_provider(
        self, mock_genai: MagicMock, model: str = "gemini-embedding-001"
    ) -> Any:
        from quantumrag.core.llm.providers.gemini import GeminiEmbeddingProvider

        with patch("quantumrag.core.llm.providers.gemini._get_genai", return_value=mock_genai):
            return GeminiEmbeddingProvider(model=model, api_key="test-key")

    def _mock_genai(self) -> MagicMock:
        mock = MagicMock()
        mock.Client.return_value = MagicMock()
        mock.types.EmbedContentConfig = MagicMock
        return mock

    def test_dimensions_default(self) -> None:
        mock_genai = self._mock_genai()
        provider = self._make_provider(mock_genai)
        assert provider.dimensions == 3072

    def test_dimensions_custom(self) -> None:
        mock_genai = self._mock_genai()
        from quantumrag.core.llm.providers.gemini import GeminiEmbeddingProvider

        with patch("quantumrag.core.llm.providers.gemini._get_genai", return_value=mock_genai):
            provider = GeminiEmbeddingProvider(
                model="gemini-embedding-001", api_key="test", dimensions=256
            )
        assert provider.dimensions == 256

    async def test_embed_empty(self) -> None:
        mock_genai = self._mock_genai()
        provider = self._make_provider(mock_genai)
        result = await provider.embed([])
        assert result == []

    async def test_embed(self) -> None:
        mock_genai = self._mock_genai()
        provider = self._make_provider(mock_genai)

        embeddings = [
            SimpleNamespace(values=[0.1, 0.2, 0.3]),
            SimpleNamespace(values=[0.4, 0.5, 0.6]),
        ]
        mock_resp = SimpleNamespace(embeddings=embeddings)
        provider._client.aio.models.embed_content = AsyncMock(return_value=mock_resp)

        with patch("quantumrag.core.llm.providers.gemini._get_genai", return_value=mock_genai):
            result = await provider.embed(["hello", "world"])

        assert len(result) == 2
        assert result[0] == [0.1, 0.2, 0.3]
        assert result[1] == [0.4, 0.5, 0.6]

    async def test_embed_query(self) -> None:
        mock_genai = self._mock_genai()
        provider = self._make_provider(mock_genai)

        embeddings = [SimpleNamespace(values=[0.1, 0.2])]
        mock_resp = SimpleNamespace(embeddings=embeddings)
        provider._client.aio.models.embed_content = AsyncMock(return_value=mock_resp)

        with patch("quantumrag.core.llm.providers.gemini._get_genai", return_value=mock_genai):
            result = await provider.embed_query("hello")

        assert result == [0.1, 0.2]


# ---------------------------------------------------------------------------
# Error conversion
# ---------------------------------------------------------------------------


class TestGeminiErrorConversion:
    def test_auth_error_invalid_key(self) -> None:
        from quantumrag.core.llm.providers.gemini import _convert_gemini_error

        exc = Exception("Invalid API key. Please pass a valid API_KEY_INVALID api key.")
        result = _convert_gemini_error(exc)
        assert isinstance(result, LLMAuthenticationError)

    def test_auth_error_permission_denied(self) -> None:
        from quantumrag.core.llm.providers.gemini import _convert_gemini_error

        exc = Exception("Permission denied for this resource")
        result = _convert_gemini_error(exc)
        assert isinstance(result, LLMAuthenticationError)

    def test_rate_limit_error(self) -> None:
        from quantumrag.core.llm.providers.gemini import _convert_gemini_error

        exc = Exception("429 Resource has been exhausted (quota exceeded)")
        result = _convert_gemini_error(exc)
        assert isinstance(result, LLMRateLimitError)

    def test_not_found_error(self) -> None:
        from quantumrag.core.llm.providers.gemini import _convert_gemini_error

        exc = Exception("404 Model not found: gemini-99")
        result = _convert_gemini_error(exc)
        assert isinstance(result, LLMModelNotFoundError)

    def test_unknown_error_passthrough(self) -> None:
        from quantumrag.core.llm.providers.gemini import _convert_gemini_error

        exc = ValueError("some random error")
        result = _convert_gemini_error(exc)
        assert result is exc
