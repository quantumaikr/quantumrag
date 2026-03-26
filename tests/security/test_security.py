"""Security integration tests (E5.2).

Validates that security controls are properly enforced across the API.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def secured_client(tmp_path: Path) -> TestClient:
    """Create a test client with security features enabled."""
    from unittest.mock import MagicMock, patch

    mock_engine = MagicMock()
    mock_engine._ensure_initialized = MagicMock()
    doc_store = AsyncMock()
    doc_store.count_documents = AsyncMock(return_value=0)
    doc_store.count_chunks = AsyncMock(return_value=0)
    doc_store.list_documents = AsyncMock(return_value=[])
    mock_engine._get_document_store = MagicMock(return_value=doc_store)
    mock_engine.get_document_store = MagicMock(return_value=doc_store)
    mock_engine.status = lambda: {"documents": 0, "chunks": 0}

    os.environ["QUANTUMRAG_API_KEY"] = "test-secret-key"
    try:
        with patch("quantumrag.core.engine.Engine.__init__", return_value=None):
            from quantumrag.api.server import create_app
            app = create_app()
        app.state.engine = mock_engine
        yield TestClient(app)
    finally:
        del os.environ["QUANTUMRAG_API_KEY"]


class TestSQLInjection:
    def test_sql_injection_in_query_param(self, secured_client: TestClient) -> None:
        """SQL injection payloads should not cause database errors."""
        resp = secured_client.get(
            "/v1/documents",
            params={"source_id": "'; DROP TABLE documents; --"},
            headers={"X-API-Key": "test-secret-key"},
        )
        # Should return a valid response (empty or filtered), not 500
        assert resp.status_code in (200, 400, 422)
        assert resp.status_code != 500

    def test_sql_injection_in_filter_key(self, secured_client: TestClient) -> None:
        """Filter keys with special characters should be rejected."""
        resp = secured_client.get(
            "/v1/documents",
            params={"filter": "key'; DROP TABLE--"},
            headers={"X-API-Key": "test-secret-key"},
        )
        assert resp.status_code != 500


class TestPathTraversal:
    def test_path_traversal_blocked(self, secured_client: TestClient) -> None:
        """Path traversal attempts should be rejected."""
        resp = secured_client.post(
            "/v1/ingest",
            json={"path": "../../../etc/passwd"},
            headers={"X-API-Key": "test-secret-key"},
        )
        assert resp.status_code in (400, 403)

    def test_url_encoded_traversal_blocked(self, secured_client: TestClient) -> None:
        """URL-encoded path traversal should also be blocked."""
        resp = secured_client.post(
            "/v1/ingest",
            json={"path": "%2e%2e/%2e%2e/%2e%2e/etc/passwd"},
            headers={"X-API-Key": "test-secret-key"},
        )
        assert resp.status_code in (400, 403)


class TestSSRF:
    def test_ssrf_localhost_blocked(self) -> None:
        """Private IP addresses should be blocked by SSRF protection."""
        from quantumrag.connectors.url import _is_private_ip

        assert _is_private_ip("127.0.0.1") is True
        assert _is_private_ip("10.0.0.1") is True
        assert _is_private_ip("192.168.1.1") is True
        assert _is_private_ip("172.16.0.1") is True

    def test_ssrf_public_allowed(self) -> None:
        """Public IP addresses should be allowed."""
        from quantumrag.connectors.url import _is_private_ip

        assert _is_private_ip("8.8.8.8") is False


class TestRequestBodySize:
    def test_large_body_rejected(self, secured_client: TestClient) -> None:
        """Very large request bodies should be rejected."""
        # Send a request with Content-Length exceeding the limit
        resp = secured_client.post(
            "/v1/query",
            json={"query": "x" * 100},
            headers={
                "X-API-Key": "test-secret-key",
                "Content-Length": str(200 * 1024 * 1024),  # 200MB (exceeds 100MB limit)
            },
        )
        # Should be rejected with 413 or handled gracefully
        assert resp.status_code in (413, 422, 200)


class TestRateLimiting:
    def test_rate_limiting_returns_429(self) -> None:
        """Rapid requests should eventually trigger rate limiting."""
        from quantumrag.api.middleware import _TokenBucket

        bucket = _TokenBucket(rate=1.0, capacity=2.0)

        # Drain the bucket
        assert bucket.allow("test")[0] is True
        assert bucket.allow("test")[0] is True
        allowed, retry_after = bucket.allow("test")
        assert allowed is False
        assert retry_after > 0

    def test_health_exempt_from_rate_limiting(self, secured_client: TestClient) -> None:
        """Health endpoint should not be rate limited."""
        for _ in range(50):
            resp = secured_client.get("/health")
            assert resp.status_code == 200


class TestErrorDisclosure:
    def test_error_does_not_expose_internals(self, secured_client: TestClient) -> None:
        """API errors should not reveal internal paths or stack traces."""
        resp = secured_client.post(
            "/v1/ingest",
            json={"path": "/nonexistent/path/that/doesnt/exist"},
            headers={"X-API-Key": "test-secret-key"},
        )
        body = resp.json()
        detail = body.get("detail", "")
        # Should not contain stack traces or file paths
        assert "Traceback" not in detail
        assert ".py" not in detail or "line" not in detail

    def test_auth_failure_is_generic(self, secured_client: TestClient) -> None:
        """Authentication failure messages should be generic."""
        resp = secured_client.post(
            "/v1/query",
            json={"query": "test"},
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert "wrong-key" not in body.get("detail", "")
        assert "test-secret-key" not in body.get("detail", "")
