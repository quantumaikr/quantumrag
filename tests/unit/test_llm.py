"""Tests for LLM provider interfaces and implementations."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from quantumrag.core.errors import GenerationError
from quantumrag.core.llm.base import (
    LLMResponse,
    UsageTracker,
    _is_retryable,
    estimate_cost,
    measure_latency,
    with_retry,
)

# ---------------------------------------------------------------------------
# LLMResponse
# ---------------------------------------------------------------------------


class TestLLMResponse:
    def test_creation(self) -> None:
        resp = LLMResponse(
            text="hello",
            tokens_in=10,
            tokens_out=5,
            estimated_cost=0.001,
            model="gpt-5.4-nano",
            latency_ms=123.4,
        )
        assert resp.text == "hello"
        assert resp.tokens_in == 10
        assert resp.tokens_out == 5
        assert resp.estimated_cost == 0.001
        assert resp.model == "gpt-5.4-nano"
        assert resp.latency_ms == 123.4

    def test_frozen(self) -> None:
        resp = LLMResponse(
            text="x",
            tokens_in=1,
            tokens_out=1,
            estimated_cost=0.0,
            model="m",
            latency_ms=0.0,
        )
        with pytest.raises(AttributeError):
            resp.text = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# UsageTracker
# ---------------------------------------------------------------------------


class TestUsageTracker:
    def test_empty(self) -> None:
        tracker = UsageTracker()
        assert tracker.total_tokens_in == 0
        assert tracker.total_tokens_out == 0
        assert tracker.total_cost == 0.0
        assert tracker.call_count == 0
        assert tracker.history == []

    def test_record_single(self) -> None:
        tracker = UsageTracker()
        resp = LLMResponse(
            text="a",
            tokens_in=100,
            tokens_out=50,
            estimated_cost=0.01,
            model="m",
            latency_ms=50.0,
        )
        tracker.record(resp)
        assert tracker.total_tokens_in == 100
        assert tracker.total_tokens_out == 50
        assert tracker.total_cost == pytest.approx(0.01)
        assert tracker.call_count == 1
        assert len(tracker.history) == 1

    def test_record_multiple(self) -> None:
        tracker = UsageTracker()
        for i in range(5):
            tracker.record(
                LLMResponse(
                    text=str(i),
                    tokens_in=10,
                    tokens_out=20,
                    estimated_cost=0.002,
                    model="m",
                    latency_ms=1.0,
                )
            )
        assert tracker.total_tokens_in == 50
        assert tracker.total_tokens_out == 100
        assert tracker.total_cost == pytest.approx(0.01)
        assert tracker.call_count == 5
        assert len(tracker.history) == 5

    def test_reset(self) -> None:
        tracker = UsageTracker()
        tracker.record(
            LLMResponse(
                text="x",
                tokens_in=10,
                tokens_out=10,
                estimated_cost=0.01,
                model="m",
                latency_ms=1.0,
            )
        )
        tracker.reset()
        assert tracker.total_tokens_in == 0
        assert tracker.call_count == 0
        assert tracker.history == []


# ---------------------------------------------------------------------------
# estimate_cost / measure_latency
# ---------------------------------------------------------------------------


class TestUtilities:
    def test_estimate_cost(self) -> None:
        # 1000 input tokens at $0.10/1M = 0.0001
        # 500 output tokens at $0.40/1M = 0.0002
        cost = estimate_cost(1000, 500, 0.10, 0.40)
        assert cost == pytest.approx(0.0003)

    def test_estimate_cost_zero(self) -> None:
        assert estimate_cost(0, 0, 1.0, 1.0) == 0.0

    def test_measure_latency(self) -> None:
        elapsed = measure_latency()
        # Just verify it returns a positive number
        ms = elapsed()
        assert ms >= 0.0


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


class TestRetryLogic:
    async def test_succeeds_first_try(self) -> None:
        fn = AsyncMock(return_value="ok")
        result = await with_retry(fn, provider_name="test")
        assert result == "ok"
        assert fn.await_count == 1

    async def test_retries_on_transient_error(self) -> None:
        exc = Exception("boom")
        exc.status_code = 429  # type: ignore[attr-defined]
        fn = AsyncMock(side_effect=[exc, exc, "ok"])
        result = await with_retry(fn, max_retries=3, base_delay=0.01, provider_name="test")
        assert result == "ok"
        assert fn.await_count == 3

    async def test_raises_after_max_retries(self) -> None:
        exc = Exception("overloaded")
        exc.status_code = 503  # type: ignore[attr-defined]
        fn = AsyncMock(side_effect=exc)
        with pytest.raises(GenerationError, match="4 attempt"):
            await with_retry(fn, max_retries=3, base_delay=0.01, provider_name="test")
        assert fn.await_count == 4

    async def test_no_retry_on_non_transient(self) -> None:
        fn = AsyncMock(side_effect=ValueError("bad input"))
        with pytest.raises(GenerationError, match="1 attempt"):
            await with_retry(fn, max_retries=3, base_delay=0.01, provider_name="test")
        assert fn.await_count == 1

    def test_is_retryable_status_codes(self) -> None:
        for code in [429, 500, 502, 503, 504]:
            exc = Exception()
            exc.status_code = code  # type: ignore[attr-defined]
            assert _is_retryable(exc) is True

    def test_is_retryable_connection_error(self) -> None:
        assert _is_retryable(ConnectionError("failed")) is True
        assert _is_retryable(TimeoutError("timed out")) is True

    def test_is_not_retryable(self) -> None:
        assert _is_retryable(ValueError("bad")) is False
        assert _is_retryable(KeyError("missing")) is False


# ---------------------------------------------------------------------------
# OpenAI Provider (mocked)
# ---------------------------------------------------------------------------


class TestOpenAILLMProvider:
    def _make_provider(self, mock_openai: MagicMock, model: str = "gpt-5.4-nano") -> Any:
        from quantumrag.core.llm.providers.openai import OpenAILLMProvider

        with patch("quantumrag.core.llm.providers.openai._get_openai", return_value=mock_openai):
            return OpenAILLMProvider(model=model, api_key="test-key")

    def _mock_openai(self) -> MagicMock:
        mock = MagicMock()
        mock.AsyncOpenAI.return_value = MagicMock()
        return mock

    async def test_generate(self) -> None:
        mock_openai = self._mock_openai()
        provider = self._make_provider(mock_openai)

        # Mock the completion response
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=20)
        message = SimpleNamespace(content="Hello world")
        choice = SimpleNamespace(message=message)
        completion = SimpleNamespace(choices=[choice], usage=usage)
        provider._client.chat.completions.create = AsyncMock(return_value=completion)

        resp = await provider.generate("Hi", system="Be helpful")
        assert resp.text == "Hello world"
        assert resp.tokens_in == 10
        assert resp.tokens_out == 20
        assert resp.model == "gpt-5.4-nano"
        assert resp.estimated_cost > 0
        assert resp.latency_ms > 0

    async def test_generate_structured(self) -> None:
        mock_openai = self._mock_openai()
        provider = self._make_provider(mock_openai)

        usage = SimpleNamespace(prompt_tokens=15, completion_tokens=25)
        message = SimpleNamespace(content='{"answer": "yes"}')
        choice = SimpleNamespace(message=message)
        completion = SimpleNamespace(choices=[choice], usage=usage)
        provider._client.chat.completions.create = AsyncMock(return_value=completion)

        result = await provider.generate_structured("Is the sky blue?")
        assert result == {"answer": "yes"}

    async def test_generate_structured_invalid_json(self) -> None:
        mock_openai = self._mock_openai()
        provider = self._make_provider(mock_openai)

        usage = SimpleNamespace(prompt_tokens=5, completion_tokens=5)
        message = SimpleNamespace(content="not json at all")
        choice = SimpleNamespace(message=message)
        completion = SimpleNamespace(choices=[choice], usage=usage)
        provider._client.chat.completions.create = AsyncMock(return_value=completion)

        with pytest.raises(GenerationError, match=r"\[openai/gpt-5\.4-nano\].*invalid JSON"):
            await provider.generate_structured("test")

    async def test_missing_sdk(self) -> None:
        mock_openai = MagicMock()
        mock_openai.side_effect = ImportError("No module named 'openai'")

        with (
            patch(
                "quantumrag.core.llm.providers.openai._get_openai",
                side_effect=GenerationError("openai package is not installed", provider="openai"),
            ),
            pytest.raises(GenerationError, match="not installed"),
        ):
            from quantumrag.core.llm.providers.openai import OpenAILLMProvider

            OpenAILLMProvider(api_key="x")


class TestOpenAIEmbeddingProvider:
    def _make_provider(self, mock_openai: MagicMock, model: str = "text-embedding-3-small") -> Any:
        from quantumrag.core.llm.providers.openai import OpenAIEmbeddingProvider

        with patch("quantumrag.core.llm.providers.openai._get_openai", return_value=mock_openai):
            return OpenAIEmbeddingProvider(model=model, api_key="test-key")

    def _mock_openai(self) -> MagicMock:
        mock = MagicMock()
        mock.AsyncOpenAI.return_value = MagicMock()
        return mock

    def test_dimensions(self) -> None:
        mock_openai = self._mock_openai()
        provider = self._make_provider(mock_openai)
        assert provider.dimensions == 1536

    def test_dimensions_large(self) -> None:
        mock_openai = self._mock_openai()
        provider = self._make_provider(mock_openai, model="text-embedding-3-large")
        assert provider.dimensions == 3072

    async def test_embed_empty(self) -> None:
        mock_openai = self._mock_openai()
        provider = self._make_provider(mock_openai)
        result = await provider.embed([])
        assert result == []

    async def test_embed(self) -> None:
        mock_openai = self._mock_openai()
        provider = self._make_provider(mock_openai)

        embed_data = [
            SimpleNamespace(embedding=[0.1, 0.2, 0.3], index=0),
            SimpleNamespace(embedding=[0.4, 0.5, 0.6], index=1),
        ]
        mock_resp = SimpleNamespace(data=embed_data)
        provider._client.embeddings.create = AsyncMock(return_value=mock_resp)

        result = await provider.embed(["hello", "world"])
        assert len(result) == 2
        assert result[0] == [0.1, 0.2, 0.3]
        assert result[1] == [0.4, 0.5, 0.6]

    async def test_embed_query(self) -> None:
        mock_openai = self._mock_openai()
        provider = self._make_provider(mock_openai)

        embed_data = [SimpleNamespace(embedding=[0.1, 0.2], index=0)]
        mock_resp = SimpleNamespace(data=embed_data)
        provider._client.embeddings.create = AsyncMock(return_value=mock_resp)

        result = await provider.embed_query("hello")
        assert result == [0.1, 0.2]

    async def test_batch_splitting(self) -> None:
        """Verify that large embedding lists are split into batches."""
        from quantumrag.core.llm.providers.openai import _EMBEDDING_BATCH_SIZE

        mock_openai = self._mock_openai()
        provider = self._make_provider(mock_openai)

        total = _EMBEDDING_BATCH_SIZE + 10
        texts = [f"text-{i}" for i in range(total)]

        def make_response(**kwargs: Any) -> SimpleNamespace:
            input_batch = kwargs.get("input", [])
            data = [SimpleNamespace(embedding=[float(i)], index=i) for i in range(len(input_batch))]
            return SimpleNamespace(data=data)

        provider._client.embeddings.create = AsyncMock(side_effect=make_response)

        result = await provider.embed(texts)
        assert len(result) == total
        # Should have been called twice (batch split)
        assert provider._client.embeddings.create.await_count == 2


# ---------------------------------------------------------------------------
# Anthropic Provider (mocked)
# ---------------------------------------------------------------------------


class TestAnthropicLLMProvider:
    def _make_provider(
        self, mock_anthropic: MagicMock, model: str = "claude-sonnet-4-20250514"
    ) -> Any:
        from quantumrag.core.llm.providers.anthropic import AnthropicLLMProvider

        with patch(
            "quantumrag.core.llm.providers.anthropic._get_anthropic",
            return_value=mock_anthropic,
        ):
            return AnthropicLLMProvider(model=model, api_key="test-key")

    def _mock_anthropic(self) -> MagicMock:
        mock = MagicMock()
        mock.AsyncAnthropic.return_value = MagicMock()
        return mock

    async def test_generate(self) -> None:
        mock_anthropic = self._mock_anthropic()
        provider = self._make_provider(mock_anthropic)

        text_block = SimpleNamespace(text="Hello from Claude")
        usage = SimpleNamespace(input_tokens=15, output_tokens=10)
        resp = SimpleNamespace(content=[text_block], usage=usage)
        provider._client.messages.create = AsyncMock(return_value=resp)

        result = await provider.generate("Hi")
        assert result.text == "Hello from Claude"
        assert result.tokens_in == 15
        assert result.tokens_out == 10
        assert result.model == "claude-sonnet-4-20250514"
        assert result.estimated_cost > 0

    async def test_generate_structured(self) -> None:
        mock_anthropic = self._mock_anthropic()
        provider = self._make_provider(mock_anthropic)

        text_block = SimpleNamespace(text='{"result": 42}')
        usage = SimpleNamespace(input_tokens=10, output_tokens=5)
        resp = SimpleNamespace(content=[text_block], usage=usage)
        provider._client.messages.create = AsyncMock(return_value=resp)

        result = await provider.generate_structured("What is 6*7?")
        assert result == {"result": 42}

    async def test_generate_structured_strips_fences(self) -> None:
        mock_anthropic = self._mock_anthropic()
        provider = self._make_provider(mock_anthropic)

        text_block = SimpleNamespace(text='```json\n{"ok": true}\n```')
        usage = SimpleNamespace(input_tokens=10, output_tokens=5)
        resp = SimpleNamespace(content=[text_block], usage=usage)
        provider._client.messages.create = AsyncMock(return_value=resp)

        result = await provider.generate_structured("test")
        assert result == {"ok": True}

    async def test_cache_control_in_kwargs(self) -> None:
        mock_anthropic = self._mock_anthropic()
        provider = self._make_provider(mock_anthropic)

        # Verify cache_control is added to system prompt
        kwargs = provider._build_kwargs("hello", "system prompt", 0.1, 2048)
        assert isinstance(kwargs["system"], list)
        assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}


# ---------------------------------------------------------------------------
# Ollama Provider (mocked)
# ---------------------------------------------------------------------------


class TestOllamaLLMProvider:
    def _make_provider(self, mock_httpx: MagicMock, model: str = "llama3.1") -> Any:
        from quantumrag.core.llm.providers.ollama import OllamaLLMProvider

        with patch("quantumrag.core.llm.providers.ollama._get_httpx", return_value=mock_httpx):
            return OllamaLLMProvider(model=model)

    def _mock_httpx(self) -> MagicMock:
        mock = MagicMock()
        mock.AsyncClient.return_value = MagicMock()
        mock.Timeout.return_value = MagicMock()
        return mock

    async def test_generate(self) -> None:
        mock_httpx = self._mock_httpx()
        provider = self._make_provider(mock_httpx)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "message": {"content": "Local model reply"},
            "prompt_eval_count": 20,
            "eval_count": 15,
        }
        mock_resp.raise_for_status = MagicMock()
        provider._client.post = AsyncMock(return_value=mock_resp)

        result = await provider.generate("Hi")
        assert result.text == "Local model reply"
        assert result.tokens_in == 20
        assert result.tokens_out == 15
        assert result.estimated_cost == 0.0
        assert result.model == "llama3.1"

    async def test_generate_structured(self) -> None:
        mock_httpx = self._mock_httpx()
        provider = self._make_provider(mock_httpx)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "message": {"content": '{"answer": "local"}'},
            "prompt_eval_count": 10,
            "eval_count": 5,
        }
        mock_resp.raise_for_status = MagicMock()
        provider._client.post = AsyncMock(return_value=mock_resp)

        result = await provider.generate_structured("test")
        assert result == {"answer": "local"}

    async def test_connection_failure(self) -> None:
        mock_httpx = self._mock_httpx()
        # Create a ConnectError class on the mock
        mock_httpx.ConnectError = type("ConnectError", (ConnectionError,), {})
        provider = self._make_provider(mock_httpx)

        provider._client.post = AsyncMock(side_effect=mock_httpx.ConnectError("Connection refused"))

        with pytest.raises(GenerationError, match=r"\[ollama\]"):
            await provider.generate("Hi")


class TestOllamaEmbeddingProvider:
    def _make_provider(self, mock_httpx: MagicMock) -> Any:
        from quantumrag.core.llm.providers.ollama import OllamaEmbeddingProvider

        with patch("quantumrag.core.llm.providers.ollama._get_httpx", return_value=mock_httpx):
            return OllamaEmbeddingProvider(model="nomic-embed-text")

    def _mock_httpx(self) -> MagicMock:
        mock = MagicMock()
        mock.AsyncClient.return_value = MagicMock()
        mock.Timeout.return_value = MagicMock()
        return mock

    def test_dimensions(self) -> None:
        mock_httpx = self._mock_httpx()
        provider = self._make_provider(mock_httpx)
        assert provider.dimensions == 768

    async def test_embed(self) -> None:
        mock_httpx = self._mock_httpx()
        provider = self._make_provider(mock_httpx)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "embeddings": [[0.1, 0.2], [0.3, 0.4]],
        }
        mock_resp.raise_for_status = MagicMock()
        provider._client.post = AsyncMock(return_value=mock_resp)

        result = await provider.embed(["hello", "world"])
        assert len(result) == 2
        assert result[0] == [0.1, 0.2]

    async def test_embed_empty(self) -> None:
        mock_httpx = self._mock_httpx()
        provider = self._make_provider(mock_httpx)
        result = await provider.embed([])
        assert result == []
