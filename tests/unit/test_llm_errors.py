"""Tests for LLM error standardization, rate limiting, and HyPE retry logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from quantumrag.core.errors import (
    LLMAuthenticationError,
    LLMContextLengthError,
    LLMModelNotFoundError,
    LLMProviderError,
    LLMRateLimitError,
    QuantumRAGError,
)

# ---------------------------------------------------------------------------
# 1. Test LLM error types
# ---------------------------------------------------------------------------


class TestLLMAuthenticationError:
    def test_basic_creation(self) -> None:
        err = LLMAuthenticationError("openai")
        assert err.provider == "openai"
        assert isinstance(err, QuantumRAGError)
        assert "openai" in str(err)
        assert "Authentication" in str(err)

    def test_default_hint(self) -> None:
        err = LLMAuthenticationError("anthropic")
        assert "API key" in err.suggestion


class TestLLMRateLimitError:
    def test_basic_creation(self) -> None:
        err = LLMRateLimitError("openai", retry_after_seconds=30.0)
        assert err.provider == "openai"
        assert err.retry_after_seconds == 30.0
        assert isinstance(err, QuantumRAGError)

    def test_without_retry_after(self) -> None:
        err = LLMRateLimitError("anthropic")
        assert err.retry_after_seconds is None
        assert "Rate limit" in str(err)

    def test_suggestion_includes_retry(self) -> None:
        err = LLMRateLimitError("openai", retry_after_seconds=60.0)
        assert "60" in err.suggestion


class TestLLMModelNotFoundError:
    def test_basic_creation(self) -> None:
        err = LLMModelNotFoundError("openai", "gpt-99")
        assert err.provider == "openai"
        assert err.model == "gpt-99"
        assert isinstance(err, QuantumRAGError)

    def test_with_available_models(self) -> None:
        err = LLMModelNotFoundError(
            "openai", "gpt-99", available_models=["gpt-4o", "gpt-4o-mini"]
        )
        assert "gpt-4o" in err.suggestion
        assert err.available_models == ["gpt-4o", "gpt-4o-mini"]

    def test_without_available_models(self) -> None:
        err = LLMModelNotFoundError("openai", "gpt-99")
        assert err.available_models == []


class TestLLMContextLengthError:
    def test_basic_creation(self) -> None:
        err = LLMContextLengthError(
            "openai", max_tokens=4096, requested_tokens=8000
        )
        assert err.provider == "openai"
        assert err.max_tokens == 4096
        assert err.requested_tokens == 8000
        assert isinstance(err, QuantumRAGError)

    def test_suggestion_content(self) -> None:
        err = LLMContextLengthError(
            "anthropic", max_tokens=100000, requested_tokens=200000
        )
        assert "200000" in err.suggestion
        assert "100000" in err.suggestion


class TestLLMProviderError:
    def test_basic_creation(self) -> None:
        orig = RuntimeError("something broke")
        err = LLMProviderError("openai", orig)
        assert err.provider == "openai"
        assert err.original_error is orig
        assert isinstance(err, QuantumRAGError)

    def test_with_string_error(self) -> None:
        err = LLMProviderError("ollama", "connection refused")
        assert "connection refused" in str(err)

    def test_custom_suggestion(self) -> None:
        err = LLMProviderError(
            "ollama",
            "connect error",
            suggestion="Is Ollama running?",
        )
        assert err.suggestion == "Is Ollama running?"


class TestLLMErrorHierarchy:
    def test_all_inherit_from_quantumrag_error(self) -> None:
        errors = [
            LLMAuthenticationError("p"),
            LLMRateLimitError("p"),
            LLMModelNotFoundError("p", "m"),
            LLMContextLengthError("p"),
            LLMProviderError("p", "e"),
        ]
        for err in errors:
            assert isinstance(err, QuantumRAGError)
            assert isinstance(err, Exception)


# ---------------------------------------------------------------------------
# 2. Test OpenAI error conversion
# ---------------------------------------------------------------------------


class TestOpenAIErrorConversion:
    def _make_openai_error(self, cls_name: str, message: str = "test"):
        """Create a mock openai exception."""
        mock_mod = MagicMock()
        # Create exception classes that inherit from Exception
        base = type("APIError", (Exception,), {"status_code": 500})
        mock_mod.APIError = base
        mock_mod.AuthenticationError = type("AuthenticationError", (base,), {"status_code": 401})
        mock_mod.RateLimitError = type("RateLimitError", (base,), {"status_code": 429})
        mock_mod.NotFoundError = type("NotFoundError", (base,), {"status_code": 404})
        mock_mod.BadRequestError = type("BadRequestError", (base,), {"status_code": 400})
        return mock_mod, getattr(mock_mod, cls_name)(message)

    def test_authentication_error(self) -> None:
        mock_mod, exc = self._make_openai_error("AuthenticationError")
        with patch(
            "quantumrag.core.llm.providers.openai._get_openai", return_value=mock_mod
        ):
            from quantumrag.core.llm.providers.openai import _convert_openai_error

            result = _convert_openai_error(exc)
            assert isinstance(result, LLMAuthenticationError)
            assert result.provider == "openai"

    def test_rate_limit_error(self) -> None:
        mock_mod, exc = self._make_openai_error("RateLimitError")
        exc.headers = {"retry-after": "30"}
        with patch(
            "quantumrag.core.llm.providers.openai._get_openai", return_value=mock_mod
        ):
            from quantumrag.core.llm.providers.openai import _convert_openai_error

            result = _convert_openai_error(exc)
            assert isinstance(result, LLMRateLimitError)

    def test_not_found_error(self) -> None:
        mock_mod, exc = self._make_openai_error("NotFoundError")
        with patch(
            "quantumrag.core.llm.providers.openai._get_openai", return_value=mock_mod
        ):
            from quantumrag.core.llm.providers.openai import _convert_openai_error

            result = _convert_openai_error(exc)
            assert isinstance(result, LLMModelNotFoundError)

    def test_bad_request_context_length(self) -> None:
        mock_mod, exc = self._make_openai_error(
            "BadRequestError", "maximum context length exceeded"
        )
        with patch(
            "quantumrag.core.llm.providers.openai._get_openai", return_value=mock_mod
        ):
            from quantumrag.core.llm.providers.openai import _convert_openai_error

            result = _convert_openai_error(exc)
            assert isinstance(result, LLMContextLengthError)

    def test_bad_request_generic(self) -> None:
        mock_mod, exc = self._make_openai_error("BadRequestError", "invalid param")
        with patch(
            "quantumrag.core.llm.providers.openai._get_openai", return_value=mock_mod
        ):
            from quantumrag.core.llm.providers.openai import _convert_openai_error

            result = _convert_openai_error(exc)
            assert isinstance(result, LLMProviderError)

    def test_generic_api_error(self) -> None:
        mock_mod, exc = self._make_openai_error("APIError", "server error")
        with patch(
            "quantumrag.core.llm.providers.openai._get_openai", return_value=mock_mod
        ):
            from quantumrag.core.llm.providers.openai import _convert_openai_error

            result = _convert_openai_error(exc)
            assert isinstance(result, LLMProviderError)

    def test_non_openai_error_passthrough(self) -> None:
        mock_mod = MagicMock()
        mock_mod.APIError = type("APIError", (Exception,), {})
        mock_mod.AuthenticationError = type("AuthenticationError", (mock_mod.APIError,), {})
        mock_mod.RateLimitError = type("RateLimitError", (mock_mod.APIError,), {})
        mock_mod.NotFoundError = type("NotFoundError", (mock_mod.APIError,), {})
        mock_mod.BadRequestError = type("BadRequestError", (mock_mod.APIError,), {})

        exc = ValueError("unrelated")
        with patch(
            "quantumrag.core.llm.providers.openai._get_openai", return_value=mock_mod
        ):
            from quantumrag.core.llm.providers.openai import _convert_openai_error

            result = _convert_openai_error(exc)
            assert isinstance(result, ValueError)


# ---------------------------------------------------------------------------
# 3. Test Anthropic error conversion
# ---------------------------------------------------------------------------


class TestAnthropicErrorConversion:
    def _make_anthropic_error(self, cls_name: str, message: str = "test"):
        mock_mod = MagicMock()
        base = type("APIError", (Exception,), {"status_code": 500})
        mock_mod.APIError = base
        mock_mod.AuthenticationError = type("AuthenticationError", (base,), {"status_code": 401})
        mock_mod.RateLimitError = type("RateLimitError", (base,), {"status_code": 429})
        mock_mod.NotFoundError = type("NotFoundError", (base,), {"status_code": 404})
        mock_mod.BadRequestError = type("BadRequestError", (base,), {"status_code": 400})
        return mock_mod, getattr(mock_mod, cls_name)(message)

    def test_authentication_error(self) -> None:
        mock_mod, exc = self._make_anthropic_error("AuthenticationError")
        with patch(
            "quantumrag.core.llm.providers.anthropic._get_anthropic",
            return_value=mock_mod,
        ):
            from quantumrag.core.llm.providers.anthropic import (
                _convert_anthropic_error,
            )

            result = _convert_anthropic_error(exc)
            assert isinstance(result, LLMAuthenticationError)
            assert result.provider == "anthropic"

    def test_rate_limit_error(self) -> None:
        mock_mod, exc = self._make_anthropic_error("RateLimitError")
        with patch(
            "quantumrag.core.llm.providers.anthropic._get_anthropic",
            return_value=mock_mod,
        ):
            from quantumrag.core.llm.providers.anthropic import (
                _convert_anthropic_error,
            )

            result = _convert_anthropic_error(exc)
            assert isinstance(result, LLMRateLimitError)

    def test_not_found_error(self) -> None:
        mock_mod, exc = self._make_anthropic_error("NotFoundError")
        with patch(
            "quantumrag.core.llm.providers.anthropic._get_anthropic",
            return_value=mock_mod,
        ):
            from quantumrag.core.llm.providers.anthropic import (
                _convert_anthropic_error,
            )

            result = _convert_anthropic_error(exc)
            assert isinstance(result, LLMModelNotFoundError)

    def test_bad_request_context_length(self) -> None:
        mock_mod, exc = self._make_anthropic_error(
            "BadRequestError", "too many tokens in request"
        )
        with patch(
            "quantumrag.core.llm.providers.anthropic._get_anthropic",
            return_value=mock_mod,
        ):
            from quantumrag.core.llm.providers.anthropic import (
                _convert_anthropic_error,
            )

            result = _convert_anthropic_error(exc)
            assert isinstance(result, LLMContextLengthError)

    def test_bad_request_generic(self) -> None:
        mock_mod, exc = self._make_anthropic_error("BadRequestError", "invalid")
        with patch(
            "quantumrag.core.llm.providers.anthropic._get_anthropic",
            return_value=mock_mod,
        ):
            from quantumrag.core.llm.providers.anthropic import (
                _convert_anthropic_error,
            )

            result = _convert_anthropic_error(exc)
            assert isinstance(result, LLMProviderError)

    def test_generic_api_error(self) -> None:
        mock_mod, exc = self._make_anthropic_error("APIError")
        with patch(
            "quantumrag.core.llm.providers.anthropic._get_anthropic",
            return_value=mock_mod,
        ):
            from quantumrag.core.llm.providers.anthropic import (
                _convert_anthropic_error,
            )

            result = _convert_anthropic_error(exc)
            assert isinstance(result, LLMProviderError)


# ---------------------------------------------------------------------------
# 4. Test Ollama error conversion
# ---------------------------------------------------------------------------


class TestOllamaErrorConversion:
    @pytest.mark.asyncio
    async def test_connection_error_becomes_provider_error(self) -> None:
        """Ollama ConnectError should produce LLMProviderError with Ollama hint."""
        import httpx

        from quantumrag.core.llm.providers.ollama import OllamaLLMProvider

        provider = OllamaLLMProvider(model="llama3.1", base_url="http://localhost:11434")

        # Mock the client to raise ConnectError
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        provider._client = mock_client

        with pytest.raises(LLMProviderError) as exc_info:
            await provider._post("/api/chat", {"model": "llama3.1"})
        assert "Ollama running" in exc_info.value.suggestion

    @pytest.mark.asyncio
    async def test_404_becomes_model_not_found(self) -> None:
        """Ollama HTTP 404 should produce LLMModelNotFoundError."""
        from quantumrag.core.llm.providers.ollama import OllamaLLMProvider

        provider = OllamaLLMProvider(model="nonexistent", base_url="http://localhost:11434")

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        provider._client = mock_client

        with pytest.raises(LLMModelNotFoundError) as exc_info:
            await provider._post("/api/chat", {"model": "nonexistent"})
        assert exc_info.value.model == "nonexistent"


# ---------------------------------------------------------------------------
# 5. Test rate limiter Retry-After header
# ---------------------------------------------------------------------------


class TestRateLimiterRetryAfter:
    def test_retry_after_header_on_429(self) -> None:
        """When rate limit is exceeded, response should include Retry-After header."""
        from quantumrag.api.middleware import _TokenBucket

        # Create a bucket with very low capacity
        bucket = _TokenBucket(rate=1.0, capacity=1.0)

        # First request should succeed
        allowed, retry_after = bucket.allow("test-key")
        assert allowed is True
        assert retry_after == 0.0

        # Second immediate request should be rejected with retry_after > 0
        allowed, retry_after = bucket.allow("test-key")
        assert allowed is False
        assert retry_after > 0.0

    def test_retry_after_header_in_middleware(self) -> None:
        """Full integration test: 429 response includes Retry-After header."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from quantumrag.api.middleware import setup_rate_limiting

        app = FastAPI()

        @app.get("/test")
        async def _test_endpoint():
            return {"ok": True}

        # Very restrictive: 1 req/s, capacity 1
        setup_rate_limiting(app, rate=1.0, capacity=1.0)

        client = TestClient(app)

        # First request passes
        resp1 = client.get("/test")
        assert resp1.status_code == 200

        # Second request should be rate-limited
        resp2 = client.get("/test")
        assert resp2.status_code == 429
        assert "Retry-After" in resp2.headers
        retry_val = int(resp2.headers["Retry-After"])
        assert retry_val >= 1


# ---------------------------------------------------------------------------
# 6. Test per-API-key rate limiting
# ---------------------------------------------------------------------------


class TestPerApiKeyRateLimiting:
    def test_different_api_keys_have_separate_buckets(self) -> None:
        """Different API keys should have independent rate limits."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from quantumrag.api.middleware import setup_rate_limiting

        app = FastAPI()

        @app.get("/test")
        async def _test_endpoint():
            return {"ok": True}

        setup_rate_limiting(app, rate=1.0, capacity=1.0)
        client = TestClient(app)

        # Key A: first request
        resp = client.get("/test", headers={"X-API-Key": "key-a"})
        assert resp.status_code == 200

        # Key A: second request (should be limited)
        resp = client.get("/test", headers={"X-API-Key": "key-a"})
        assert resp.status_code == 429

        # Key B: first request (different bucket, should pass)
        resp = client.get("/test", headers={"X-API-Key": "key-b"})
        assert resp.status_code == 200

    def test_no_api_key_uses_ip(self) -> None:
        """Requests without API key should be rate-limited by IP."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from quantumrag.api.middleware import setup_rate_limiting

        app = FastAPI()

        @app.get("/test")
        async def _test_endpoint():
            return {"ok": True}

        setup_rate_limiting(app, rate=1.0, capacity=1.0)
        client = TestClient(app)

        # No API key: first request
        resp = client.get("/test")
        assert resp.status_code == 200

        # No API key: second request (same IP, should be limited)
        resp = client.get("/test")
        assert resp.status_code == 429


# ---------------------------------------------------------------------------
# 7. Test HyPE retry logic and threshold
# ---------------------------------------------------------------------------


class TestHyPERetryLogic:
    @pytest.mark.asyncio
    async def test_retry_on_failure(self) -> None:
        """HyPE generation should retry up to 2 times with backoff."""
        from quantumrag.core.ingest.indexer.triple_index_builder import (
            TripleIndexBuilder,
        )
        from quantumrag.core.models import Chunk

        call_count = 0

        async def mock_generate_structured(prompt, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("LLM failure")
            return {"questions": ["Q1", "Q2", "Q3"]}

        async def mock_generate(prompt, **kwargs):
            raise RuntimeError("also fails")

        mock_llm = MagicMock()
        mock_llm.generate_structured = AsyncMock(side_effect=mock_generate_structured)
        mock_llm.generate = AsyncMock(side_effect=mock_generate)

        builder = TripleIndexBuilder(
            vector_store=MagicMock(),
            hype_vector_store=MagicMock(),
            bm25_store=MagicMock(),
            embedding_provider=MagicMock(),
            llm_provider=mock_llm,
        )

        chunk = Chunk(content="Test content", document_id="doc1", chunk_index=0)

        # Patch sleep to avoid waiting
        with patch("asyncio.sleep", new_callable=AsyncMock):
            questions = await builder._generate_hype_questions_with_retry(chunk)

        assert len(questions) == 3
        assert call_count == 3  # 2 failures + 1 success

    @pytest.mark.asyncio
    async def test_all_retries_exhausted(self) -> None:
        """When all retries fail, should return empty list."""
        from quantumrag.core.ingest.indexer.triple_index_builder import (
            TripleIndexBuilder,
        )
        from quantumrag.core.models import Chunk

        async def always_fail(prompt, **kwargs):
            raise RuntimeError("permanent failure")

        mock_llm = MagicMock()
        mock_llm.generate_structured = AsyncMock(side_effect=always_fail)
        mock_llm.generate = AsyncMock(side_effect=always_fail)

        builder = TripleIndexBuilder(
            vector_store=MagicMock(),
            hype_vector_store=MagicMock(),
            bm25_store=MagicMock(),
            embedding_provider=MagicMock(),
            llm_provider=mock_llm,
        )

        chunk = Chunk(content="Test content", document_id="doc1", chunk_index=0)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            questions = await builder._generate_hype_questions_with_retry(chunk)

        assert questions == []

    @pytest.mark.asyncio
    async def test_hype_coverage_ratio_in_report(self) -> None:
        """IndexingReport should include hype_coverage_ratio."""
        from quantumrag.core.ingest.indexer.triple_index_builder import (
            IndexingReport,
            TripleIndexBuilder,
        )
        from quantumrag.core.models import Chunk

        call_idx = 0

        async def sometimes_fail(prompt, **kwargs):
            nonlocal call_idx
            call_idx += 1
            # Fail for odd calls (to make some chunks fail entirely)
            if call_idx % 4 == 0:
                raise RuntimeError("fail")
            return {"questions": ["Q1"]}

        mock_llm = MagicMock()
        mock_llm.generate_structured = AsyncMock(side_effect=sometimes_fail)
        mock_llm.generate = AsyncMock(side_effect=RuntimeError("no fallback"))

        mock_embed = AsyncMock()
        mock_embed.embed = AsyncMock(return_value=[[0.1, 0.2]])

        mock_vs = AsyncMock()
        mock_vs.add_vectors = AsyncMock()

        builder = TripleIndexBuilder(
            vector_store=mock_vs,
            hype_vector_store=mock_vs,
            bm25_store=AsyncMock(),
            embedding_provider=mock_embed,
            llm_provider=mock_llm,
        )

        chunks = [
            Chunk(content=f"Chunk {i}", document_id="doc1", chunk_index=i)
            for i in range(5)
        ]

        report = IndexingReport()
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await builder._build_hype_embeddings(chunks, report)

        assert 0.0 <= report.hype_coverage_ratio <= 1.0

    def test_indexing_report_has_coverage_field(self) -> None:
        """IndexingReport should have hype_coverage_ratio with default 1.0."""
        from quantumrag.core.ingest.indexer.triple_index_builder import (
            IndexingReport,
        )

        report = IndexingReport()
        assert hasattr(report, "hype_coverage_ratio")
        assert report.hype_coverage_ratio == 1.0

    @pytest.mark.asyncio
    async def test_failure_threshold_warning(self) -> None:
        """When >20% chunks fail HyPE, a warning should be logged."""
        from quantumrag.core.ingest.indexer.triple_index_builder import (
            IndexingReport,
            TripleIndexBuilder,
        )
        from quantumrag.core.models import Chunk

        # All chunks fail
        async def always_fail(prompt, **kwargs):
            raise RuntimeError("fail")

        mock_llm = MagicMock()
        mock_llm.generate_structured = AsyncMock(side_effect=always_fail)
        mock_llm.generate = AsyncMock(side_effect=always_fail)

        builder = TripleIndexBuilder(
            vector_store=AsyncMock(),
            hype_vector_store=AsyncMock(),
            bm25_store=AsyncMock(),
            embedding_provider=AsyncMock(),
            llm_provider=mock_llm,
        )

        chunks = [
            Chunk(content=f"Chunk {i}", document_id="doc1", chunk_index=i)
            for i in range(5)
        ]
        report = IndexingReport()

        with (
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch(
                "quantumrag.core.ingest.indexer.triple_index_builder.logger"
            ) as mock_logger,
        ):
            await builder._build_hype_embeddings(chunks, report)

        # Should have logged a warning about threshold
        mock_logger.warning.assert_any_call(
            "hype_failure_threshold_exceeded",
            total_chunks=5,
            failed_chunks=5,
            coverage_ratio=0.0,
        )
        assert report.hype_coverage_ratio == 0.0
