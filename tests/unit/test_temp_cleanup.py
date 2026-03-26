"""Tests for temporary file cleanup in connectors (E1.5)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from quantumrag.connectors.gdrive import GoogleDriveConnector
from quantumrag.connectors.notion import NotionConnector
from quantumrag.connectors.s3 import S3Connector

# ---------------------------------------------------------------------------
# Google Drive
# ---------------------------------------------------------------------------


class TestGoogleDriveCleanup:
    def _make_connector(self) -> GoogleDriveConnector:
        connector = GoogleDriveConnector(credentials_path="fake.json")
        return connector

    @pytest.mark.asyncio
    async def test_temp_dir_cleaned_on_context_exit(self) -> None:
        connector = self._make_connector()

        # Simulate fetch_document without calling the real Google API
        mock_service = MagicMock()
        meta_resp = {"name": "test.pdf", "mimeType": "application/pdf"}
        mock_service.files().get().execute.return_value = meta_resp
        mock_service.files().get_media.return_value = MagicMock()
        connector._service = mock_service

        with patch(
            "asyncio.to_thread",
            return_value=(b"fake pdf content", "test.pdf"),
        ):
            async with connector:
                path = await connector.fetch_document("file-123")
                assert path.exists()
                temp_dir = path.parent

            # After exiting the context manager, temp dir should be removed
            assert not temp_dir.exists()

    @pytest.mark.asyncio
    async def test_explicit_cleanup(self) -> None:
        connector = self._make_connector()
        connector._service = MagicMock()

        with patch(
            "asyncio.to_thread",
            return_value=(b"data", "doc.txt"),
        ):
            path = await connector.fetch_document("file-456")
            temp_dir = path.parent
            assert temp_dir.exists()

            connector.cleanup()
            assert not temp_dir.exists()

    @pytest.mark.asyncio
    async def test_custom_download_dir_not_tracked(self) -> None:
        """When the caller provides download_dir, the connector should not track it."""
        connector = self._make_connector()
        connector._service = MagicMock()

        with tempfile.TemporaryDirectory() as user_dir:
            with patch(
                "asyncio.to_thread",
                return_value=(b"data", "doc.txt"),
            ):
                path = await connector.fetch_document("file-789", download_dir=Path(user_dir))
                assert path.exists()

            # No temp dirs tracked
            assert len(connector._temp_dirs) == 0


# ---------------------------------------------------------------------------
# Notion
# ---------------------------------------------------------------------------


class TestNotionCleanup:
    @staticmethod
    def _make_mock_httpx() -> MagicMock:
        """Create a mock httpx module with AsyncClient that returns empty blocks."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"results": [], "has_more": False}

        mock_async_client = AsyncMock()
        mock_async_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        mock_httpx = MagicMock()
        mock_httpx.AsyncClient.return_value = mock_async_client
        return mock_httpx

    @pytest.mark.asyncio
    async def test_temp_dir_cleaned_on_context_exit(self) -> None:
        connector = NotionConnector(api_key="fake-key")
        mock_httpx = self._make_mock_httpx()

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            async with connector:
                path = await connector.fetch_document("page-abc")
                assert path.exists()
                temp_dir = path.parent

            assert not temp_dir.exists()

    @pytest.mark.asyncio
    async def test_explicit_cleanup(self) -> None:
        connector = NotionConnector(api_key="fake-key")
        mock_httpx = self._make_mock_httpx()

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            path = await connector.fetch_document("page-def")
            temp_dir = path.parent
            assert temp_dir.exists()

            connector.cleanup()
            assert not temp_dir.exists()


# ---------------------------------------------------------------------------
# S3
# ---------------------------------------------------------------------------


class TestS3Cleanup:
    def _make_connector(self) -> S3Connector:
        connector = S3Connector(bucket="test-bucket")
        return connector

    @pytest.mark.asyncio
    async def test_temp_dir_cleaned_on_context_exit(self) -> None:
        connector = self._make_connector()
        mock_client = MagicMock()
        connector._client = mock_client

        with patch(
            "asyncio.to_thread",
            return_value=b"s3 file bytes",
        ):
            async with connector:
                path = await connector.fetch_document("docs/file.pdf")
                assert path.exists()
                temp_dir = path.parent

            assert not temp_dir.exists()

    @pytest.mark.asyncio
    async def test_explicit_cleanup(self) -> None:
        connector = self._make_connector()
        connector._client = MagicMock()

        with patch(
            "asyncio.to_thread",
            return_value=b"s3 data",
        ):
            path = await connector.fetch_document("key.txt")
            temp_dir = path.parent
            assert temp_dir.exists()

            connector.cleanup()
            assert not temp_dir.exists()

    @pytest.mark.asyncio
    async def test_multiple_fetches_all_cleaned(self) -> None:
        connector = self._make_connector()
        connector._client = MagicMock()

        dirs: list[Path] = []
        with patch("asyncio.to_thread", return_value=b"data"):
            for i in range(3):
                path = await connector.fetch_document(f"file{i}.txt")
                dirs.append(path.parent)

        assert len(connector._temp_dirs) == 3
        for d in dirs:
            assert d.exists()

        connector.cleanup()
        for d in dirs:
            assert not d.exists()
        assert len(connector._temp_dirs) == 0
