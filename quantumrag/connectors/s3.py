"""AWS S3 connector (requires boto3)."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from quantumrag.connectors.gdrive import ConnectorDocument, SyncResult
from quantumrag.core.logging import get_logger

logger = get_logger("quantumrag.connectors.s3")


class S3Connector:
    """Connect to S3 for document ingestion.

    Requires: boto3
    Install with: pip install boto3

    Supports the context-manager protocol for automatic temp-file cleanup::

        async with S3Connector(bucket="my-bucket") as s3:
            path = await s3.fetch_document("path/to/key.pdf")
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        **kwargs: Any,
    ) -> None:
        self._bucket = bucket
        self._prefix = prefix
        self._boto_kwargs = kwargs
        self._client: Any = None
        self._temp_dirs: list[tempfile.TemporaryDirectory[str]] = []

    # -- context-manager support ------------------------------------------

    def __enter__(self) -> S3Connector:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.cleanup()

    async def __aenter__(self) -> S3Connector:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        """Remove all temporary directories created by :meth:`fetch_document`."""
        for td in self._temp_dirs:
            td.cleanup()
        self._temp_dirs.clear()

    def _get_client(self) -> Any:
        """Lazy-initialize the S3 client."""
        if self._client is not None:
            return self._client

        try:
            import boto3
        except ImportError as e:
            raise ImportError("S3 connector requires boto3. Install with: pip install boto3") from e

        self._client = boto3.client("s3", **self._boto_kwargs)
        return self._client

    async def list_documents(self, prefix: str | None = None) -> list[ConnectorDocument]:
        """List objects in the S3 bucket under the given prefix."""
        client = self._get_client()
        target_prefix = prefix or self._prefix

        def _list() -> list[dict[str, Any]]:
            items: list[dict[str, Any]] = []
            paginator = client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=self._bucket, Prefix=target_prefix)
            for page in pages:
                for obj in page.get("Contents", []):
                    items.append(obj)
            return items

        objects = await asyncio.to_thread(_list)
        results: list[ConnectorDocument] = []

        for obj in objects:
            key = obj["Key"]
            # Skip "directory" markers
            if key.endswith("/"):
                continue

            name = key.rsplit("/", 1)[-1] if "/" in key else key
            modified = obj.get("LastModified")

            results.append(
                ConnectorDocument(
                    id=key,
                    name=name,
                    path=f"s3://{self._bucket}/{key}",
                    modified_at=modified,
                    size=obj.get("Size", 0),
                    mime_type=_guess_mime(name),
                )
            )

        return results

    async def fetch_document(
        self,
        key: str,
        download_dir: Path | None = None,
    ) -> Path:
        """Download a file from S3."""
        client = self._get_client()

        def _download() -> bytes:
            resp = client.get_object(Bucket=self._bucket, Key=key)
            return resp["Body"].read()

        data = await asyncio.to_thread(_download)

        if download_dir is not None:
            target_dir = download_dir
        else:
            td = tempfile.TemporaryDirectory(prefix="quantumrag_s3_")
            self._temp_dirs.append(td)
            target_dir = Path(td.name)
        target_dir.mkdir(parents=True, exist_ok=True)
        name = key.rsplit("/", 1)[-1] if "/" in key else key
        file_path = target_dir / name
        file_path.write_bytes(data)

        return file_path

    async def sync(
        self,
        last_sync: datetime | None = None,
    ) -> SyncResult:
        """Sync documents from S3."""
        result = SyncResult()
        try:
            docs = await self.list_documents()
            for doc in docs:
                if last_sync is None or (doc.modified_at and doc.modified_at > last_sync):
                    result.added += 1
        except Exception as e:
            result.errors.append(str(e))

        return result


def _guess_mime(filename: str) -> str:
    """Guess MIME type from filename extension."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mime_map = {
        "pdf": "application/pdf",
        "txt": "text/plain",
        "md": "text/markdown",
        "html": "text/html",
        "htm": "text/html",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "csv": "text/csv",
        "json": "application/json",
    }
    return mime_map.get(ext, "application/octet-stream")
