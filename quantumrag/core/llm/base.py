"""Abstract interfaces and shared utilities for LLM providers."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable

from quantumrag.core.errors import GenerationError
from quantumrag.core.logging import get_logger

logger = get_logger("quantumrag.llm")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Immutable response from an LLM provider."""

    text: str
    tokens_in: int
    tokens_out: int
    estimated_cost: float
    model: str
    latency_ms: float


@dataclass
class UsageTracker:
    """Accumulates token usage and cost across multiple calls."""

    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_cost: float = 0.0
    call_count: int = 0
    _history: list[LLMResponse] = field(default_factory=list, repr=False)

    def record(self, response: LLMResponse) -> None:
        """Record a single LLM response."""
        self.total_tokens_in += response.tokens_in
        self.total_tokens_out += response.tokens_out
        self.total_cost += response.estimated_cost
        self.call_count += 1
        self._history.append(response)

    def reset(self) -> None:
        """Reset all counters."""
        self.total_tokens_in = 0
        self.total_tokens_out = 0
        self.total_cost = 0.0
        self.call_count = 0
        self._history.clear()

    @property
    def history(self) -> list[LLMResponse]:
        return list(self._history)


# ---------------------------------------------------------------------------
# Protocols (interfaces)
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM text generation providers."""

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> LLMResponse: ...

    async def generate_stream(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]: ...

    async def generate_structured(
        self,
        prompt: str,
        *,
        schema: dict | None = None,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> dict: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol for embedding providers."""

    @property
    def dimensions(self) -> int: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, query: str) -> list[float]: ...


# ---------------------------------------------------------------------------
# Retry utility
# ---------------------------------------------------------------------------

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


async def with_retry(
    fn: Callable[..., object],
    *args: object,
    max_retries: int = 3,
    base_delay: float = 1.0,
    provider_name: str = "",
    **kwargs: object,
) -> object:
    """Execute *fn* with exponential-backoff retry.

    Only retries on transient / rate-limit errors.  All other exceptions
    propagate immediately.
    """
    for attempt in range(max_retries + 1):
        try:
            return await fn(*args, **kwargs)  # type: ignore[misc]
        except Exception as exc:
            # Decide whether the error is retryable
            retryable = _is_retryable(exc)
            if not retryable or attempt == max_retries:
                raise GenerationError(
                    f"[{provider_name}] LLM call failed after {attempt + 1} attempt(s): {exc}",
                    provider=provider_name,
                ) from exc
            delay = base_delay * (2**attempt)
            logger.warning(
                "retrying_llm_call",
                attempt=attempt + 1,
                max_retries=max_retries,
                delay=delay,
                error=str(exc),
                provider=provider_name,
            )
            await asyncio.sleep(delay)

    # Should never reach here, but satisfy the type checker.
    raise GenerationError(  # pragma: no cover
        f"[{provider_name}] LLM call failed after {max_retries + 1} attempts",
        provider=provider_name,
    )


def _is_retryable(exc: BaseException) -> bool:
    """Return True if *exc* looks like a transient / rate-limit error."""
    # Check for status_code attribute (openai / anthropic SDK errors)
    status = getattr(exc, "status_code", None)
    if status is not None and status in _RETRYABLE_STATUS_CODES:
        return True
    # httpx-level transport errors
    exc_name = type(exc).__name__
    if exc_name in {
        "ConnectError",
        "ReadTimeout",
        "ConnectTimeout",
        "RemoteProtocolError",
        "APIConnectionError",  # openai SDK connection error
    }:
        return True
    # Check parent class names (e.g., openai.APIConnectionError)
    for cls in type(exc).__mro__:
        if cls.__name__ in {"APIConnectionError", "APITimeoutError"}:
            return True
    # Generic timeout / connection errors
    return isinstance(exc, (TimeoutError, ConnectionError, OSError))


def estimate_cost(
    tokens_in: int,
    tokens_out: int,
    price_per_1m_in: float,
    price_per_1m_out: float,
) -> float:
    """Calculate estimated cost in USD from token counts and per-1M pricing."""
    return (tokens_in * price_per_1m_in + tokens_out * price_per_1m_out) / 1_000_000


def measure_latency() -> Callable[[], float]:
    """Return a callable that, when invoked, returns elapsed ms since creation."""
    start = time.perf_counter()

    def elapsed() -> float:
        return (time.perf_counter() - start) * 1000.0

    return elapsed
