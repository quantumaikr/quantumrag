"""Middleware for the QuantumRAG HTTP API."""

from __future__ import annotations

import hmac
import os
import time
import uuid
from collections import defaultdict

from typing import Any

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = structlog.get_logger("quantumrag.api")


# ---------------------------------------------------------------------------
# API key authentication
# ---------------------------------------------------------------------------


def setup_api_key_auth(app: FastAPI, api_key: str | None = None) -> None:
    """Add optional API key authentication middleware.

    The key is read from *api_key* argument, falling back to the
    ``QUANTUMRAG_API_KEY`` environment variable.  If neither is set the
    middleware is a no-op (all requests are allowed through).
    """
    resolved_key = api_key or os.environ.get("QUANTUMRAG_API_KEY")

    @app.middleware("http")
    async def _api_key_middleware(request: Request, call_next: Any) -> Response:
        if resolved_key:
            # Skip auth for docs / openapi / health-like endpoints
            if request.url.path in ("/docs", "/redoc", "/openapi.json", "/health"):
                return await call_next(request)

            provided = request.headers.get("X-API-Key") or ""
            if not hmac.compare_digest(provided, resolved_key):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing API key"},
                )
        return await call_next(request)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------


def setup_cors(
    app: FastAPI,
    allowed_origins: list[str] | None = None,
    allow_credentials: bool | None = None,
) -> None:
    """Add CORS middleware.

    By default uses permissive dev settings (all origins, no credentials).
    For production pass *allowed_origins* (e.g. ``["https://myapp.com"]``)
    and set *allow_credentials* to ``True`` if cookies/auth headers are needed.

    The ``QUANTUMRAG_CORS_ORIGINS`` environment variable (comma-separated) is
    also respected when *allowed_origins* is not provided.
    """
    env_origins = os.environ.get("QUANTUMRAG_CORS_ORIGINS")
    if allowed_origins is not None:
        origins = allowed_origins
    elif env_origins:
        origins = [o.strip() for o in env_origins.split(",") if o.strip()]
    else:
        origins = ["*"]

    # Prevent the insecure combination of wildcard origins + credentials
    if origins == ["*"]:
        credentials = False
    else:
        credentials = allow_credentials if allow_credentials is not None else True

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ---------------------------------------------------------------------------
# Request logging
# ---------------------------------------------------------------------------


def setup_request_logging(app: FastAPI) -> None:
    """Log every request with method, path, status and latency."""

    @app.middleware("http")
    async def _logging_middleware(request: Request, call_next: Any) -> Response:
        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            latency_ms=round(elapsed_ms, 1),
        )
        return response


# ---------------------------------------------------------------------------
# Request ID tracking
# ---------------------------------------------------------------------------


def setup_request_id(app: FastAPI) -> None:
    """Add request ID tracking — extracts ``X-Request-ID`` from the incoming
    request or generates a new UUID.  The ID is:

    * Injected into structlog context so all log lines include it.
    * Returned in the ``X-Request-ID`` response header.
    """

    @app.middleware("http")
    async def _request_id_middleware(request: Request, call_next: Any) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        # Store on request state for downstream access
        request.state.request_id = request_id

        with structlog.contextvars.bound_contextvars(request_id=request_id):
            response: Response = await call_next(request)

        response.headers["X-Request-ID"] = request_id
        return response


# ---------------------------------------------------------------------------
# Simple in-memory rate limiter (token bucket)
# ---------------------------------------------------------------------------

# Endpoints excluded from rate limiting
_RATE_LIMIT_EXEMPT_PATHS: frozenset[str] = frozenset(
    {"/health", "/docs", "/redoc", "/openapi.json"}
)

# Default TTL for rate-limiter entries (seconds)
_BUCKET_TTL_SECONDS: float = 3600.0  # 1 hour


class _TokenBucket:
    """Per-key token-bucket rate limiter with TTL cleanup and max-bucket eviction."""

    def __init__(
        self,
        rate: float = 10.0,
        capacity: float = 20.0,
        max_buckets: int = 10_000,
        ttl: float = _BUCKET_TTL_SECONDS,
    ) -> None:
        self.rate = rate  # tokens per second
        self.capacity = capacity
        self.max_buckets = max_buckets
        self.ttl = ttl
        self._buckets: dict[str, float] = defaultdict(lambda: capacity)
        self._last: dict[str, float] = {}

    def _cleanup_expired(self, now: float) -> None:
        """Remove entries older than *ttl* seconds."""
        cutoff = now - self.ttl
        expired = [k for k, ts in self._last.items() if ts < cutoff]
        for k in expired:
            self._last.pop(k, None)
            self._buckets.pop(k, None)

    def _evict_oldest(self) -> None:
        """Evict the oldest entry when bucket count exceeds *max_buckets*."""
        while len(self._last) > self.max_buckets:
            oldest_key = min(self._last, key=self._last.get)  # type: ignore[arg-type]
            self._last.pop(oldest_key, None)
            self._buckets.pop(oldest_key, None)

    def allow(self, key: str) -> tuple[bool, float]:
        """Check if a request is allowed.

        Returns a tuple of ``(allowed, retry_after_seconds)``.
        *retry_after_seconds* is ``0.0`` when allowed, otherwise the estimated
        seconds until a token becomes available.
        """
        now = time.monotonic()

        # Periodic housekeeping: TTL cleanup
        self._cleanup_expired(now)

        last = self._last.get(key, now)
        elapsed = now - last
        self._last[key] = now

        # Evict oldest entries *after* inserting so the new key is counted
        self._evict_oldest()

        tokens = self._buckets[key] + elapsed * self.rate
        if tokens > self.capacity:
            tokens = self.capacity
        self._buckets[key] = tokens

        if tokens >= 1.0:
            self._buckets[key] -= 1.0
            return True, 0.0

        # Calculate how long until one token is available
        deficit = 1.0 - tokens
        retry_after = deficit / self.rate if self.rate > 0 else 1.0
        return False, retry_after


def setup_rate_limiting(
    app: FastAPI,
    rate: float = 10.0,
    capacity: float = 20.0,
    max_buckets: int = 10_000,
) -> None:
    """Add a simple in-memory token-bucket rate limiter keyed by client IP."""
    bucket = _TokenBucket(rate=rate, capacity=capacity, max_buckets=max_buckets)

    @app.middleware("http")
    async def _rate_limit_middleware(request: Request, call_next: Any) -> Response:
        # Exempt health / docs endpoints from rate limiting
        if request.url.path in _RATE_LIMIT_EXEMPT_PATHS:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        # Use API key as rate-limit key when present (per-key limiting)
        api_key = request.headers.get("X-API-Key")
        rate_key = f"apikey:{api_key}" if api_key else f"ip:{client_ip}"

        allowed, retry_after = bucket.allow(rate_key)
        if not allowed:
            retry_after_int = max(1, int(retry_after + 0.5))
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please try again later."},
                headers={"Retry-After": str(retry_after_int)},
            )
        return await call_next(request)
