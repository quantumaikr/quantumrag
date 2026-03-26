"""Tests for the _run_sync async/sync bridge helper (E2.1)."""

from __future__ import annotations

import asyncio

import pytest

from quantumrag.core.engine import _run_sync


class TestRunSync:
    def test_basic_coroutine(self) -> None:
        async def add(a: int, b: int) -> int:
            return a + b

        assert _run_sync(add(3, 4)) == 7

    def test_with_async_sleep(self) -> None:
        async def delayed_value() -> str:
            await asyncio.sleep(0.01)
            return "done"

        assert _run_sync(delayed_value()) == "done"

    def test_exception_propagation(self) -> None:
        async def fail() -> None:
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            _run_sync(fail())

    def test_works_from_running_loop(self) -> None:
        """When called from within an async context (via thread), it should still work."""

        async def outer() -> str:
            # Simulate calling _run_sync from within a running event loop
            # by using loop.run_in_executor
            loop = asyncio.get_running_loop()

            def sync_call() -> str:
                async def inner() -> str:
                    return "from thread"

                return _run_sync(inner())

            return await loop.run_in_executor(None, sync_call)

        result = asyncio.run(outer())
        assert result == "from thread"
