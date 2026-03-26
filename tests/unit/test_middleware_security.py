"""Security-focused tests for Sprint E1 hotfixes.

E1.1 — Timing-safe API key comparison, no query-param auth
E1.2 — Input validation (top_k bounds, request body size limit)
E1.3 — Error response safety (no internal details leaked)
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from quantumrag.api.models import QueryRequest
from quantumrag.core.models import Confidence, EvalResult, QueryResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_engine(*, raise_on_query: Exception | None = None) -> MagicMock:
    """Build a mock Engine.  Optionally make aquery raise an exception."""
    engine = MagicMock()

    ingest_result = MagicMock()
    ingest_result.documents = 1
    ingest_result.chunks = 5
    ingest_result.elapsed_seconds = 0.5
    ingest_result.errors = []
    engine.aingest = AsyncMock(return_value=ingest_result)

    if raise_on_query:
        engine.aquery = AsyncMock(side_effect=raise_on_query)
    else:
        engine.aquery = AsyncMock(
            return_value=QueryResult(
                answer="ok",
                sources=[],
                confidence=Confidence.INSUFFICIENT_EVIDENCE,
                metadata={},
            )
        )

    engine.status.return_value = {
        "project_name": "test",
        "documents": 0,
        "chunks": 0,
        "data_dir": "/tmp",
        "embedding_model": "m",
        "language": "en",
    }
    engine.evaluate.return_value = EvalResult(summary="ok", suggestions=[])
    engine._ensure_initialized = MagicMock()
    doc_store = AsyncMock()
    doc_store.count_documents = AsyncMock(return_value=0)
    doc_store.list_documents = AsyncMock(return_value=[])
    doc_store.delete_document = AsyncMock()
    engine._get_document_store = MagicMock(return_value=doc_store)

    return engine


def _build_app(mock_engine: MagicMock) -> FastAPI:
    with patch("quantumrag.core.engine.Engine.__init__", return_value=None):
        from quantumrag.api.server import create_app

        app = create_app()
    app.state.engine = mock_engine
    return app


# ---------------------------------------------------------------------------
# E1.1 — Timing-safe API key comparison & no query-param auth
# ---------------------------------------------------------------------------


class TestTimingSafeAuth:
    """Verify API key is only accepted via header and uses hmac.compare_digest."""

    @pytest.fixture()
    def authed_client(self) -> TestClient:
        engine = _make_mock_engine()
        os.environ["QUANTUMRAG_API_KEY"] = "secret-key-123"
        try:
            app = _build_app(engine)
            yield TestClient(app)
        finally:
            del os.environ["QUANTUMRAG_API_KEY"]

    def test_header_auth_accepted(self, authed_client: TestClient):
        resp = authed_client.get("/v1/status", headers={"X-API-Key": "secret-key-123"})
        assert resp.status_code == 200

    def test_missing_key_rejected(self, authed_client: TestClient):
        resp = authed_client.get("/v1/status")
        assert resp.status_code == 401

    def test_wrong_key_rejected(self, authed_client: TestClient):
        resp = authed_client.get("/v1/status", headers={"X-API-Key": "wrong"})
        assert resp.status_code == 401

    def test_query_param_key_no_longer_accepted(self, authed_client: TestClient):
        """Query-parameter API key must NOT be accepted (E1.1 requirement)."""
        resp = authed_client.get("/v1/status?api_key=secret-key-123")
        assert resp.status_code == 401

    def test_empty_key_rejected(self, authed_client: TestClient):
        resp = authed_client.get("/v1/status", headers={"X-API-Key": ""})
        assert resp.status_code == 401

    def test_hmac_compare_digest_is_used(self):
        """Verify the middleware source uses hmac.compare_digest, not ``!=``."""
        import inspect

        from quantumrag.api import middleware

        source = inspect.getsource(middleware)
        assert "hmac.compare_digest" in source
        # The old insecure pattern should be gone:
        assert "request.query_params.get" not in source


# ---------------------------------------------------------------------------
# E1.2 — Input validation (top_k, body size)
# ---------------------------------------------------------------------------


class TestTopKValidation:
    """Boundary-value tests for QueryRequest.top_k."""

    def test_top_k_none_is_valid(self):
        req = QueryRequest(query="hello")
        assert req.top_k is None

    def test_top_k_1_is_valid(self):
        req = QueryRequest(query="hello", top_k=1)
        assert req.top_k == 1

    def test_top_k_100_is_valid(self):
        req = QueryRequest(query="hello", top_k=100)
        assert req.top_k == 100

    def test_top_k_0_rejected(self):
        with pytest.raises(ValidationError):
            QueryRequest(query="hello", top_k=0)

    def test_top_k_negative_rejected(self):
        with pytest.raises(ValidationError):
            QueryRequest(query="hello", top_k=-1)

    def test_top_k_101_rejected(self):
        with pytest.raises(ValidationError):
            QueryRequest(query="hello", top_k=101)

    def test_top_k_boundary_via_api(self):
        """End-to-end check through FastAPI."""
        engine = _make_mock_engine()
        app = _build_app(engine)
        client = TestClient(app)

        # top_k=0 should be rejected by pydantic
        resp = client.post("/v1/query", json={"query": "hi", "top_k": 0})
        assert resp.status_code == 422

        resp = client.post("/v1/query", json={"query": "hi", "top_k": 101})
        assert resp.status_code == 422

        # Valid boundary values
        resp = client.post("/v1/query", json={"query": "hi", "top_k": 1})
        assert resp.status_code == 200

        resp = client.post("/v1/query", json={"query": "hi", "top_k": 100})
        assert resp.status_code == 200


class TestBodySizeLimit:
    """Request body size limit middleware (10 MB default)."""

    @pytest.fixture()
    def client(self) -> TestClient:
        engine = _make_mock_engine()
        app = _build_app(engine)
        return TestClient(app)

    def test_small_body_accepted(self, client: TestClient):
        resp = client.post("/v1/query", json={"query": "hello"})
        assert resp.status_code == 200

    def test_oversized_content_length_rejected(self, client: TestClient):
        # Claim a body larger than 100 MB via Content-Length header
        resp = client.post(
            "/v1/query",
            json={"query": "hello"},
            headers={"Content-Length": str(101 * 1024 * 1024)},
        )
        assert resp.status_code == 413
        assert "too large" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# E1.3 — Error response safety
# ---------------------------------------------------------------------------


class TestErrorResponseSafety:
    """Internal error details must NOT be leaked to the client."""

    @pytest.fixture()
    def client_with_failing_engine(self) -> TestClient:
        secret_msg = "ConnectionError: password=hunter2 host=db.internal.corp"
        engine = _make_mock_engine(raise_on_query=RuntimeError(secret_msg))
        # Also make other methods fail with secrets
        engine.status.side_effect = RuntimeError(secret_msg)
        engine.evaluate.side_effect = RuntimeError(secret_msg)
        engine._ensure_initialized.side_effect = RuntimeError(secret_msg)
        app = _build_app(engine)
        return TestClient(app, raise_server_exceptions=False)

    def test_query_error_is_generic(self, client_with_failing_engine: TestClient):
        resp = client_with_failing_engine.post("/v1/query", json={"query": "test"})
        assert resp.status_code == 500
        body = resp.json()
        assert body["detail"] == "Internal server error"
        assert "hunter2" not in resp.text
        assert "password" not in resp.text

    def test_status_error_is_generic(self, client_with_failing_engine: TestClient):
        resp = client_with_failing_engine.get("/v1/status")
        assert resp.status_code == 500
        body = resp.json()
        assert body["detail"] == "Internal server error"
        assert "hunter2" not in resp.text

    def test_evaluate_error_is_generic(self, client_with_failing_engine: TestClient):
        resp = client_with_failing_engine.post("/v1/evaluate", json={})
        assert resp.status_code == 500
        body = resp.json()
        assert body["detail"] == "Internal server error"
        assert "hunter2" not in resp.text

    def test_documents_error_is_generic(self, client_with_failing_engine: TestClient):
        resp = client_with_failing_engine.get("/v1/documents")
        assert resp.status_code == 500
        body = resp.json()
        assert body["detail"] == "Internal server error"
        assert "hunter2" not in resp.text

    def test_delete_doc_error_is_generic(self, client_with_failing_engine: TestClient):
        resp = client_with_failing_engine.delete("/v1/documents/doc-1")
        assert resp.status_code == 500
        body = resp.json()
        assert body["detail"] == "Internal server error"
        assert "hunter2" not in resp.text
