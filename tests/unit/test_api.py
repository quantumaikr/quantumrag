"""Tests for the QuantumRAG HTTP API."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from quantumrag.api.models import (
    DocumentListResponse,
    EvaluateResponse,
    IngestResponse,
    QueryResponse,
    StatusResponse,
)
from quantumrag.core.models import Confidence, EvalResult, QueryResult, Source

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_mock_engine() -> MagicMock:
    """Build a mock Engine with sensible defaults for all methods."""
    engine = MagicMock()

    # aingest
    ingest_result = MagicMock()
    ingest_result.documents = 2
    ingest_result.chunks = 10
    ingest_result.elapsed_seconds = 1.5
    ingest_result.errors = []
    engine.aingest = AsyncMock(return_value=ingest_result)

    # aquery
    query_result = QueryResult(
        answer="The answer is 42.",
        sources=[
            Source(
                chunk_id="chunk-1",
                document_title="doc.pdf",
                excerpt="...the answer is 42...",
                relevance_score=0.95,
            )
        ],
        confidence=Confidence.STRONGLY_SUPPORTED,
        metadata={"total_latency_ms": 123.4},
    )
    engine.aquery = AsyncMock(return_value=query_result)

    # query_stream
    async def _fake_stream(query, *, top_k=None, filters=None):
        for tok in ["The ", "answer ", "is ", "42."]:
            yield tok

    engine.query_stream = _fake_stream

    # status
    engine.status.return_value = {
        "project_name": "test-project",
        "documents": 5,
        "chunks": 50,
        "data_dir": "/tmp/qr_data",
        "embedding_model": "text-embedding-3-small",
        "language": "ko",
    }

    # evaluate
    engine.evaluate.return_value = EvalResult(
        summary="All good",
        suggestions=["Add more docs"],
    )

    # _ensure_initialized / _get_document_store
    engine._ensure_initialized = MagicMock()
    doc_store = AsyncMock()
    doc_store.count_documents = AsyncMock(return_value=5)
    doc_store.count_chunks = AsyncMock(return_value=50)
    doc_store.list_documents = AsyncMock(
        return_value=[
            {"id": "doc-1", "title": "readme.md", "source_type": "file", "chunk_count": 3},
        ]
    )
    doc_store.delete_document = AsyncMock()
    engine._get_document_store = MagicMock(return_value=doc_store)

    return engine


def _build_test_app(mock_engine: MagicMock) -> FastAPI:
    """Create a FastAPI app with Engine patched out."""
    with patch("quantumrag.core.engine.Engine.__init__", return_value=None):
        from quantumrag.api.server import create_app

        app = create_app()
    # Swap the engine to our mock *after* app creation
    app.state.engine = mock_engine
    return app


@pytest.fixture()
def client() -> TestClient:
    """Create a test client with a mocked engine."""
    mock_engine = _make_mock_engine()
    app = _build_test_app(mock_engine)
    yield TestClient(app)


@pytest.fixture()
def authed_client() -> TestClient:
    """Create a test client with API key auth enabled."""
    mock_engine = _make_mock_engine()
    os.environ["QUANTUMRAG_API_KEY"] = "test-secret-key"
    try:
        app = _build_test_app(mock_engine)
        yield TestClient(app)
    finally:
        del os.environ["QUANTUMRAG_API_KEY"]


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


class TestIngestEndpoint:
    def test_ingest_success(self, client: TestClient, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        resp = client.post("/v1/ingest", json={"path": str(test_file)})
        assert resp.status_code == 200
        body = IngestResponse(**resp.json())
        assert body.documents == 2
        assert body.chunks == 10

    def test_ingest_missing_path(self, client: TestClient):
        resp = client.post("/v1/ingest", json={"path": "/nonexistent/path"})
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"].lower()

    def test_ingest_validation_error(self, client: TestClient):
        resp = client.post("/v1/ingest", json={})
        assert resp.status_code == 422  # Pydantic validation error


class TestQueryEndpoint:
    def test_query_success(self, client: TestClient):
        resp = client.post("/v1/query", json={"query": "What is the answer?"})
        assert resp.status_code == 200
        body = QueryResponse(**resp.json())
        assert body.answer == "The answer is 42."
        assert body.confidence == "strongly_supported"
        assert len(body.sources) == 1
        assert body.sources[0].chunk_id == "chunk-1"

    def test_query_with_options(self, client: TestClient):
        resp = client.post(
            "/v1/query",
            json={"query": "test", "top_k": 3, "rerank": False},
        )
        assert resp.status_code == 200

    def test_query_validation_error(self, client: TestClient):
        resp = client.post("/v1/query", json={})
        assert resp.status_code == 422


class TestQueryStreamEndpoint:
    def test_query_stream(self, client: TestClient):
        resp = client.post("/v1/query/stream", json={"query": "What is the answer?"})
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        body = resp.text
        assert "data:" in body
        assert "[DONE]" in body


class TestDocumentsEndpoint:
    def test_list_documents(self, client: TestClient):
        resp = client.get("/v1/documents")
        assert resp.status_code == 200
        body = DocumentListResponse(**resp.json())
        assert body.total == 5
        assert len(body.documents) == 1
        assert body.documents[0].id == "doc-1"

    def test_list_documents_pagination(self, client: TestClient):
        resp = client.get("/v1/documents?offset=10&limit=5")
        assert resp.status_code == 200
        body = resp.json()
        assert body["offset"] == 10
        assert body["limit"] == 5

    def test_delete_document(self, client: TestClient):
        resp = client.delete("/v1/documents/doc-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "deleted"
        assert body["document_id"] == "doc-1"


class TestStatusEndpoint:
    def test_status(self, client: TestClient):
        resp = client.get("/v1/status")
        assert resp.status_code == 200
        body = StatusResponse(**resp.json())
        assert body.project_name == "test-project"
        assert body.documents == 5
        assert body.chunks == 50


class TestEvaluateEndpoint:
    def test_evaluate(self, client: TestClient):
        resp = client.post("/v1/evaluate", json={})
        assert resp.status_code == 200
        body = EvaluateResponse(**resp.json())
        assert body.summary == "All good"
        assert "Add more docs" in body.suggestions


class TestFeedbackEndpoint:
    def test_feedback_success(self, client: TestClient):
        resp = client.post(
            "/v1/feedback",
            json={
                "query": "What is X?",
                "answer": "X is Y.",
                "rating": 5,
                "comment": "Great answer!",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_feedback_validation(self, client: TestClient):
        # Rating out of range
        resp = client.post(
            "/v1/feedback",
            json={
                "query": "q",
                "answer": "a",
                "rating": 0,
            },
        )
        assert resp.status_code == 422

    def test_feedback_missing_fields(self, client: TestClient):
        resp = client.post("/v1/feedback", json={"query": "q"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Middleware tests
# ---------------------------------------------------------------------------


class TestApiKeyAuth:
    def test_request_without_key_is_rejected(self, authed_client: TestClient):
        resp = authed_client.get("/v1/status")
        assert resp.status_code == 401

    def test_request_with_valid_key(self, authed_client: TestClient):
        resp = authed_client.get(
            "/v1/status", headers={"X-API-Key": "test-secret-key"}
        )
        assert resp.status_code == 200

    def test_request_with_wrong_key(self, authed_client: TestClient):
        resp = authed_client.get(
            "/v1/status", headers={"X-API-Key": "wrong-key"}
        )
        assert resp.status_code == 401

    def test_query_param_key_rejected(self, authed_client: TestClient):
        """Query parameter auth is no longer accepted — only header-based auth."""
        resp = authed_client.get("/v1/status?api_key=test-secret-key")
        assert resp.status_code == 401

    def test_docs_endpoint_skips_auth(self, authed_client: TestClient):
        resp = authed_client.get("/docs")
        # Should not be 401 — docs are excluded from auth
        assert resp.status_code != 401


class TestRequestValidation:
    def test_query_empty_body(self, client: TestClient):
        resp = client.post("/v1/query", json={})
        assert resp.status_code == 422

    def test_ingest_empty_body(self, client: TestClient):
        resp = client.post("/v1/ingest", json={})
        assert resp.status_code == 422

    def test_feedback_rating_too_high(self, client: TestClient):
        resp = client.post(
            "/v1/feedback",
            json={"query": "q", "answer": "a", "rating": 6},
        )
        assert resp.status_code == 422

    def test_feedback_rating_too_low(self, client: TestClient):
        resp = client.post(
            "/v1/feedback",
            json={"query": "q", "answer": "a", "rating": 0},
        )
        assert resp.status_code == 422


class TestApiModelValidation:
    """Tests for Pydantic model field validation."""

    def test_query_empty_string_rejected(self, client: TestClient):
        resp = client.post("/v1/query", json={"query": ""})
        assert resp.status_code == 422

    def test_query_too_long_rejected(self, client: TestClient):
        resp = client.post("/v1/query", json={"query": "x" * 10001})
        assert resp.status_code == 422

    def test_query_max_length_accepted(self, client: TestClient):
        resp = client.post("/v1/query", json={"query": "x" * 10000})
        assert resp.status_code == 200

    def test_ingest_empty_path_rejected(self, client: TestClient):
        resp = client.post("/v1/ingest", json={"path": ""})
        assert resp.status_code == 422

    def test_feedback_empty_query_rejected(self, client: TestClient):
        resp = client.post(
            "/v1/feedback",
            json={"query": "", "answer": "a", "rating": 3},
        )
        assert resp.status_code == 422

    def test_feedback_empty_answer_rejected(self, client: TestClient):
        resp = client.post(
            "/v1/feedback",
            json={"query": "q", "answer": "", "rating": 3},
        )
        assert resp.status_code == 422
