"""SSE (Server-Sent Events) streaming helper for QuantumRAG API."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any


async def sse_stream(token_iterator: AsyncIterator[str]) -> AsyncIterator[str]:
    """Wrap an async token iterator into SSE-formatted events.

    Each token is sent as a ``data:`` event. A final ``[DONE]`` sentinel is
    sent when the stream is exhausted.
    """
    async for token in token_iterator:
        payload = json.dumps({"token": token})
        yield f"data: {payload}\n\n"
    yield "data: [DONE]\n\n"


def sse_event(data: dict[str, Any], event: str | None = None) -> str:
    """Format a single SSE event string."""
    parts: list[str] = []
    if event:
        parts.append(f"event: {event}")
    parts.append(f"data: {json.dumps(data)}")
    return "\n".join(parts) + "\n\n"
