"""Google Drive connector (requires google-api-python-client)."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from quantumrag.core.logging import get_logger

logger = get_logger("quantumrag.connectors.gdrive")


class ConnectorDocument:
    """Lightweight document reference from a connector."""

    __slots__ = ("id", "mime_type", "modified_at", "name", "path", "size")

    def __init__(
        self,
        id: str,
        name: str,
        path: str = "",
        modified_at: datetime | None = None,
        size: int = 0,
        mime_type: str = "",
    ) -> None:
        self.id = id
        self.name = name
        self.path = path
        self.modified_at = modified_at
        self.size = size
        self.mime_type = mime_type


class SyncResult:
    """Result of a connector sync operation."""

    __slots__ = ("added", "deleted", "errors", "updated")

    def __init__(
        self,
        added: int = 0,
        updated: int = 0,
        deleted: int = 0,
        errors: list[str] | None = None,
    ) -> None:
        self.added = added
        self.updated = updated
        self.deleted = deleted
        self.errors = errors or []


class GoogleDriveConnector:
    """Connect to Google Drive for document ingestion.

    Requires: google-api-python-client, google-auth-httplib2, google-auth-oauthlib
    Install with: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib

    Supports the context-manager protocol for automatic temp-file cleanup::

        async with GoogleDriveConnector(credentials_path="creds.json") as gd:
            path = await gd.fetch_document("file-id")
    """

    def __init__(
        self,
        credentials_path: str | None = None,
        folder_id: str | None = None,
    ) -> None:
        self._credentials_path = credentials_path
        self._folder_id = folder_id
        self._service: Any = None
        self._temp_dirs: list[tempfile.TemporaryDirectory[str]] = []

    # -- context-manager support ------------------------------------------

    def __enter__(self) -> GoogleDriveConnector:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.cleanup()

    async def __aenter__(self) -> GoogleDriveConnector:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        """Remove all temporary directories created by :meth:`fetch_document`."""
        for td in self._temp_dirs:
            td.cleanup()
        self._temp_dirs.clear()

    def _get_service(self) -> Any:
        """Lazy-initialize the Google Drive API service."""
        if self._service is not None:
            return self._service

        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build
        except ImportError as e:
            raise ImportError(
                "Google Drive connector requires google-api-python-client. "
                "Install with: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
            ) from e

        if self._credentials_path:
            creds = Credentials.from_service_account_file(
                self._credentials_path,
                scopes=["https://www.googleapis.com/auth/drive.readonly"],
            )
        else:
            raise ValueError("credentials_path is required for GoogleDriveConnector")

        self._service = build("drive", "v3", credentials=creds)
        return self._service

    async def list_documents(
        self,
        folder_id: str | None = None,
    ) -> list[ConnectorDocument]:
        """List documents in a Google Drive folder."""
        service = self._get_service()
        target_folder = folder_id or self._folder_id

        query = "trashed = false"
        if target_folder:
            query += f" and '{target_folder}' in parents"

        results: list[ConnectorDocument] = []

        def _list() -> list[dict[str, Any]]:
            items: list[dict[str, Any]] = []
            page_token = None
            while True:
                resp = (
                    service.files()
                    .list(
                        q=query,
                        pageSize=100,
                        fields="nextPageToken, files(id, name, mimeType, modifiedTime, size)",
                        pageToken=page_token,
                    )
                    .execute()
                )
                items.extend(resp.get("files", []))
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
            return items

        items = await asyncio.to_thread(_list)

        for item in items:
            modified = None
            if item.get("modifiedTime"):
                modified = datetime.fromisoformat(item["modifiedTime"].replace("Z", "+00:00"))
            results.append(
                ConnectorDocument(
                    id=item["id"],
                    name=item.get("name", ""),
                    path=item.get("name", ""),
                    modified_at=modified,
                    size=int(item.get("size", 0)),
                    mime_type=item.get("mimeType", ""),
                )
            )

        return results

    async def fetch_document(
        self,
        file_id: str,
        download_dir: Path | None = None,
    ) -> Path:
        """Download a file from Google Drive.

        Returns the path to the downloaded file.
        """
        service = self._get_service()

        def _fetch() -> tuple[bytes, str]:
            import io

            from googleapiclient.http import MediaIoBaseDownload

            # Get file metadata
            meta = service.files().get(fileId=file_id, fields="name,mimeType").execute()
            name = meta.get("name", file_id)

            # Handle Google Docs export
            mime = meta.get("mimeType", "")
            if mime.startswith("application/vnd.google-apps"):
                export_mime = "application/pdf"
                request = service.files().export_media(fileId=file_id, mimeType=export_mime)
                name += ".pdf"
            else:
                request = service.files().get_media(fileId=file_id)

            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

            return buffer.getvalue(), name

        data, name = await asyncio.to_thread(_fetch)

        if download_dir is not None:
            target_dir = download_dir
        else:
            td = tempfile.TemporaryDirectory(prefix="quantumrag_gdrive_")
            self._temp_dirs.append(td)
            target_dir = Path(td.name)
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / name
        file_path.write_bytes(data)

        return file_path

    async def sync(
        self,
        last_sync: datetime | None = None,
    ) -> SyncResult:
        """Sync documents from Google Drive since last sync.

        Returns a SyncResult with counts of added/updated/deleted documents.
        """
        result = SyncResult()
        try:
            docs = await self.list_documents()
            for doc in docs:
                if last_sync is None or (doc.modified_at and doc.modified_at > last_sync):
                    result.added += 1
        except Exception as e:
            result.errors.append(str(e))

        return result
