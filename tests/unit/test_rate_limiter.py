"""Tests for Sprint E3.2 — Rate limiter improvements.

Covers:
- TTL-based cleanup of expired entries
- Maximum bucket count with oldest-entry eviction
- Exclusion of /health and /docs from rate limiting
- Retry-After header on 429 responses
"""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from quantumrag.api.middleware import _TokenBucket, setup_rate_limiting

# ---------------------------------------------------------------------------
# Unit tests for _TokenBucket
# ---------------------------------------------------------------------------


class TestTokenBucketTTL:
    """Entries older than TTL should be cleaned up automatically."""

    def test_expired_entries_are_removed(self):
        bucket = _TokenBucket(rate=10.0, capacity=20.0, max_buckets=10_000, ttl=60.0)

        # Simulate an old entry by manipulating _last directly
        fake_now = time.monotonic()
        bucket._last["old-key"] = fake_now - 120  # 2 minutes ago (> 60s TTL)
        bucket._buckets["old-key"] = 5.0

        # A new allow() call should trigger cleanup
        bucket.allow("new-key")
        assert "old-key" not in bucket._last
        assert "old-key" not in bucket._buckets

    def test_recent_entries_are_kept(self):
        bucket = _TokenBucket(rate=10.0, capacity=20.0, max_buckets=10_000, ttl=60.0)

        bucket.allow("fresh-key")
        bucket.allow("another-key")

        assert "fresh-key" in bucket._last
        assert "another-key" in bucket._last


class TestTokenBucketMaxBuckets:
    """When bucket count exceeds max_buckets, oldest entries are evicted."""

    def test_eviction_at_capacity(self):
        bucket = _TokenBucket(rate=100.0, capacity=100.0, max_buckets=3, ttl=3600.0)

        # Insert 3 keys — at capacity
        bucket.allow("key-1")
        bucket.allow("key-2")
        bucket.allow("key-3")
        assert len(bucket._last) == 3

        # 4th key should evict the oldest (key-1)
        bucket.allow("key-4")
        assert len(bucket._last) <= 3
        assert "key-1" not in bucket._last

    def test_eviction_removes_oldest_not_newest(self):
        bucket = _TokenBucket(rate=100.0, capacity=100.0, max_buckets=2, ttl=3600.0)

        bucket.allow("first")
        bucket.allow("second")
        bucket.allow("third")

        # "first" should have been evicted, but "second" and "third" remain
        assert "first" not in bucket._last
        assert "third" in bucket._last


class TestTokenBucketAllow:
    """Basic allow/deny behaviour."""

    def test_initial_request_allowed(self):
        bucket = _TokenBucket(rate=10.0, capacity=1.0)
        allowed, retry_after = bucket.allow("k")
        assert allowed is True
        assert retry_after == 0.0

    def test_burst_exhaustion(self):
        bucket = _TokenBucket(rate=0.1, capacity=1.0)
        # First request exhausts the single token
        bucket.allow("k")
        # Second should be denied
        allowed, retry_after = bucket.allow("k")
        assert allowed is False
        assert retry_after > 0


# ---------------------------------------------------------------------------
# Integration tests via TestClient
# ---------------------------------------------------------------------------


def _make_rate_limited_app(rate: float = 1.0, capacity: float = 1.0) -> FastAPI:
    """Build a minimal FastAPI app with rate limiting enabled."""
    app = FastAPI()
    setup_rate_limiting(app, rate=rate, capacity=capacity)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/docs")
    async def docs():
        return {"docs": True}

    @app.get("/v1/status")
    async def status():
        return {"status": "running"}

    return app


class TestRateLimitExemptPaths:
    """/health and /docs should never receive 429."""

    @pytest.fixture()
    def client(self) -> TestClient:
        # Very restrictive: 0 capacity means every normal request is denied
        app = _make_rate_limited_app(rate=0.001, capacity=1.0)
        return TestClient(app)

    def test_health_exempt(self, client: TestClient):
        # Exhaust the bucket on a normal endpoint first
        client.get("/v1/status")
        client.get("/v1/status")
        # /health should still work
        for _ in range(5):
            resp = client.get("/health")
            assert resp.status_code == 200

    def test_docs_exempt(self, client: TestClient):
        client.get("/v1/status")
        client.get("/v1/status")
        for _ in range(5):
            resp = client.get("/docs")
            assert resp.status_code == 200


class TestRetryAfterHeader:
    """429 responses must include a Retry-After header."""

    def test_retry_after_present_on_429(self):
        app = _make_rate_limited_app(rate=0.001, capacity=1.0)
        client = TestClient(app)

        # First request uses the single token
        client.get("/v1/status")
        # Second request should be rate-limited
        resp = client.get("/v1/status")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        retry_val = int(resp.headers["Retry-After"])
        assert retry_val >= 1

    def test_retry_after_is_integer(self):
        app = _make_rate_limited_app(rate=0.5, capacity=1.0)
        client = TestClient(app)

        client.get("/v1/status")
        resp = client.get("/v1/status")
        if resp.status_code == 429:
            # Must be a valid integer
            int(resp.headers["Retry-After"])
