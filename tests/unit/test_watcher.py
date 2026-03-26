"""Tests for file system watcher and health endpoint."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quantumrag.core.watcher import SUPPORTED_EXTENSIONS, FileWatcher, _PollingBackend


class TestPollingBackend:
    """Unit tests for the polling-based watcher backend."""

    def test_detects_new_file(self, tmp_path: Path) -> None:
        backend = _PollingBackend(tmp_path, recursive=True)
        backend.start()

        # No changes yet
        added, modified, deleted = backend.poll_events()
        assert len(added) == 0

        # Create a new supported file
        new_file = tmp_path / "doc.txt"
        new_file.write_text("hello")

        added, modified, deleted = backend.poll_events()
        assert new_file in added
        assert len(modified) == 0
        assert len(deleted) == 0

    def test_detects_modification(self, tmp_path: Path) -> None:
        existing = tmp_path / "doc.md"
        existing.write_text("original")

        backend = _PollingBackend(tmp_path, recursive=True)
        backend.start()

        # Force a different mtime (some filesystems have 1s resolution)
        time.sleep(0.05)
        existing.write_text("updated")
        # Ensure mtime changes on platforms with coarse resolution
        import os
        os.utime(existing, (time.time() + 10, time.time() + 10))

        added, modified, _deleted = backend.poll_events()
        assert existing in modified
        assert len(added) == 0

    def test_detects_deletion(self, tmp_path: Path) -> None:
        to_delete = tmp_path / "remove.pdf"
        to_delete.write_text("data")

        backend = _PollingBackend(tmp_path, recursive=True)
        backend.start()

        to_delete.unlink()

        _added, _modified, deleted = backend.poll_events()
        assert to_delete in deleted

    def test_filters_unsupported_extensions(self, tmp_path: Path) -> None:
        backend = _PollingBackend(tmp_path, recursive=True)
        backend.start()

        # Create a file with an unsupported extension
        unsupported = tmp_path / "image.png"
        unsupported.write_text("not a doc")

        # Also create a supported file
        supported = tmp_path / "notes.txt"
        supported.write_text("text")

        added, _modified, _deleted = backend.poll_events()
        assert supported in added
        assert unsupported not in added


class TestFileWatcher:
    """Integration-style tests for the async FileWatcher."""

    @pytest.mark.asyncio
    async def test_detects_new_file(self, tmp_path: Path) -> None:
        changes: list[tuple[list[Path], list[Path], list[Path]]] = []

        async def callback(
            added: list[Path], modified: list[Path], deleted: list[Path],
        ) -> None:
            changes.append((added, modified, deleted))

        watcher = FileWatcher(
            tmp_path, callback, debounce_seconds=0.1, poll_interval=0.05,
        )
        await watcher.start()
        try:
            new_file = tmp_path / "new.txt"
            new_file.write_text("content")

            # Wait for debounce + poll cycles
            await asyncio.sleep(0.5)
        finally:
            await watcher.stop()

        assert len(changes) >= 1
        all_added = [p for batch in changes for p in batch[0]]
        assert new_file in all_added

    @pytest.mark.asyncio
    async def test_detects_modification(self, tmp_path: Path) -> None:
        existing = tmp_path / "exist.md"
        existing.write_text("v1")

        changes: list[tuple[list[Path], list[Path], list[Path]]] = []

        async def callback(
            added: list[Path], modified: list[Path], deleted: list[Path],
        ) -> None:
            changes.append((added, modified, deleted))

        watcher = FileWatcher(
            tmp_path, callback, debounce_seconds=0.1, poll_interval=0.05,
        )
        await watcher.start()
        try:
            await asyncio.sleep(0.1)  # let initial snapshot settle
            existing.write_text("v2")
            import os
            os.utime(existing, (time.time() + 10, time.time() + 10))
            await asyncio.sleep(0.5)
        finally:
            await watcher.stop()

        assert len(changes) >= 1
        all_modified = [p for batch in changes for p in batch[1]]
        assert existing in all_modified

    @pytest.mark.asyncio
    async def test_debounce_batches_changes(self, tmp_path: Path) -> None:
        """Multiple rapid changes should be batched into fewer callbacks."""
        callback_count = 0

        async def callback(
            added: list[Path], modified: list[Path], deleted: list[Path],
        ) -> None:
            nonlocal callback_count
            callback_count += 1

        watcher = FileWatcher(
            tmp_path, callback, debounce_seconds=0.3, poll_interval=0.05,
        )
        await watcher.start()
        try:
            # Create several files in quick succession
            for i in range(5):
                (tmp_path / f"file{i}.txt").write_text(f"content {i}")
                await asyncio.sleep(0.02)

            # Wait for debounce to fire
            await asyncio.sleep(0.8)
        finally:
            await watcher.stop()

        # All 5 rapid creates should be batched, not 5 separate callbacks
        assert callback_count >= 1
        # With debounce=0.3s and rapid creates, expect batching into 1-2 callbacks
        assert callback_count <= 3

    @pytest.mark.asyncio
    async def test_extension_filter(self, tmp_path: Path) -> None:
        changes: list[tuple[list[Path], list[Path], list[Path]]] = []

        async def callback(
            added: list[Path], modified: list[Path], deleted: list[Path],
        ) -> None:
            changes.append((added, modified, deleted))

        watcher = FileWatcher(
            tmp_path, callback, debounce_seconds=0.1, poll_interval=0.05,
        )
        await watcher.start()
        try:
            (tmp_path / "photo.jpg").write_text("binary")
            (tmp_path / "script.py").write_text("print(1)")
            (tmp_path / "real.docx").write_text("doc content")
            await asyncio.sleep(0.5)
        finally:
            await watcher.stop()

        all_added = [p for batch in changes for p in batch[0]]
        added_names = {p.name for p in all_added}
        assert "real.docx" in added_names
        assert "photo.jpg" not in added_names
        assert "script.py" not in added_names

    @pytest.mark.asyncio
    async def test_stop_start_lifecycle(self, tmp_path: Path) -> None:
        async def noop(
            added: list[Path], modified: list[Path], deleted: list[Path],
        ) -> None:
            pass

        watcher = FileWatcher(tmp_path, noop)
        assert not watcher.running
        await watcher.start()
        assert watcher.running
        await watcher.stop()
        assert not watcher.running

    def test_supported_extensions_matches_incremental(self) -> None:
        """Ensure SUPPORTED_EXTENSIONS matches the canonical set."""
        expected = {
            ".txt", ".md", ".pdf", ".docx", ".doc",
            ".xlsx", ".xls", ".pptx", ".ppt",
            ".html", ".htm", ".csv", ".json",
            ".hwp", ".hwpx",
        }
        assert expected == SUPPORTED_EXTENSIONS


class TestHealthEndpoint:
    """Tests for the GET /health endpoint."""

    def test_health_returns_correct_format(self) -> None:
        from fastapi.testclient import TestClient

        # Engine and QuantumRAGConfig are imported inside create_app, patch at source
        with (
            patch("quantumrag.core.engine.Engine") as mock_engine_cls,
            patch("quantumrag.core.config.QuantumRAGConfig") as mock_config_cls,
            patch("quantumrag.api.server.setup_cors"),
            patch("quantumrag.api.server.setup_request_logging"),
            patch("quantumrag.api.server.setup_rate_limiting"),
            patch("quantumrag.api.server.setup_api_key_auth"),
        ):
            mock_cfg = MagicMock()
            mock_cfg.storage.data_dir = "/tmp/test"
            mock_config_cls.default.return_value = mock_cfg

            mock_engine = MagicMock()
            mock_engine.status.return_value = {"documents": 42, "chunks": 256}
            mock_engine_cls.return_value = mock_engine

            from quantumrag.api.server import create_app

            app = create_app()
            client = TestClient(app)

            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()

            assert data["status"] == "healthy"
            assert "version" in data
            assert isinstance(data["uptime_seconds"], (int, float))
            assert data["uptime_seconds"] >= 0
            assert data["storage"]["documents"] == 42
            assert data["storage"]["chunks"] == 256

    def test_health_survives_engine_error(self) -> None:
        from fastapi.testclient import TestClient

        with (
            patch("quantumrag.core.engine.Engine") as mock_engine_cls,
            patch("quantumrag.core.config.QuantumRAGConfig") as mock_config_cls,
            patch("quantumrag.api.server.setup_cors"),
            patch("quantumrag.api.server.setup_request_logging"),
            patch("quantumrag.api.server.setup_rate_limiting"),
            patch("quantumrag.api.server.setup_api_key_auth"),
        ):
            mock_cfg = MagicMock()
            mock_cfg.storage.data_dir = "/tmp/test"
            mock_config_cls.default.return_value = mock_cfg

            mock_engine = MagicMock()
            mock_engine.status.side_effect = RuntimeError("db down")
            mock_engine_cls.return_value = mock_engine

            from quantumrag.api.server import create_app

            app = create_app()
            client = TestClient(app)

            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["storage"]["documents"] == 0
            assert data["storage"]["chunks"] == 0
