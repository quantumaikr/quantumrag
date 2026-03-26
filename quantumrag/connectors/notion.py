"""Notion connector (requires httpx for API calls)."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from quantumrag.connectors.gdrive import ConnectorDocument, SyncResult
from quantumrag.core.logging import get_logger

logger = get_logger("quantumrag.connectors.notion")

_NOTION_API_URL = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"


class NotionConnector:
    """Connect to Notion for document ingestion.

    Requires: httpx
    Install with: pip install httpx

    Supports the context-manager protocol for automatic temp-file cleanup::

        async with NotionConnector(api_key="secret") as nc:
            path = await nc.fetch_document("page-id")
    """

    def __init__(
        self,
        api_key: str | None = None,
        database_id: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("NOTION_API_KEY", "")
        self._database_id = database_id
        self._temp_dirs: list[tempfile.TemporaryDirectory[str]] = []

    # -- context-manager support ------------------------------------------

    def __enter__(self) -> NotionConnector:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.cleanup()

    async def __aenter__(self) -> NotionConnector:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        """Remove all temporary directories created by :meth:`fetch_document`."""
        for td in self._temp_dirs:
            td.cleanup()
        self._temp_dirs.clear()

    def _get_headers(self) -> dict[str, str]:
        if not self._api_key:
            raise ValueError(
                "Notion API key is required. Set NOTION_API_KEY env var or pass api_key."
            )
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Notion-Version": _NOTION_VERSION,
            "Content-Type": "application/json",
        }

    async def list_documents(
        self,
        database_id: str | None = None,
    ) -> list[ConnectorDocument]:
        """List pages in a Notion database."""
        try:
            import httpx
        except ImportError as e:
            raise ImportError(
                "Notion connector requires httpx. Install with: pip install httpx"
            ) from e

        target_db = database_id or self._database_id
        if not target_db:
            raise ValueError("database_id is required to list documents")

        url = f"{_NOTION_API_URL}/databases/{target_db}/query"
        results: list[ConnectorDocument] = []

        async with httpx.AsyncClient() as client:
            has_more = True
            start_cursor: str | None = None

            while has_more:
                body: dict[str, Any] = {}
                if start_cursor:
                    body["start_cursor"] = start_cursor

                resp = await client.post(url, headers=self._get_headers(), json=body)
                resp.raise_for_status()
                data = resp.json()

                for page in data.get("results", []):
                    title = _extract_title(page)
                    modified = None
                    if page.get("last_edited_time"):
                        modified = datetime.fromisoformat(
                            page["last_edited_time"].replace("Z", "+00:00")
                        )

                    results.append(
                        ConnectorDocument(
                            id=page["id"],
                            name=title,
                            path=page.get("url", ""),
                            modified_at=modified,
                            mime_type="text/markdown",
                        )
                    )

                has_more = data.get("has_more", False)
                start_cursor = data.get("next_cursor")

        return results

    async def fetch_document(
        self,
        page_id: str,
        download_dir: Path | None = None,
    ) -> Path:
        """Fetch a Notion page's content as markdown."""
        try:
            import httpx
        except ImportError as e:
            raise ImportError(
                "Notion connector requires httpx. Install with: pip install httpx"
            ) from e

        # Fetch page blocks
        url = f"{_NOTION_API_URL}/blocks/{page_id}/children"
        blocks_text: list[str] = []

        async with httpx.AsyncClient() as client:
            has_more = True
            start_cursor: str | None = None

            while has_more:
                params: dict[str, str] = {}
                if start_cursor:
                    params["start_cursor"] = start_cursor

                resp = await client.get(url, headers=self._get_headers(), params=params)
                resp.raise_for_status()
                data = resp.json()

                for block in data.get("results", []):
                    text = _block_to_text(block)
                    if text:
                        blocks_text.append(text)

                has_more = data.get("has_more", False)
                start_cursor = data.get("next_cursor")

        content = "\n\n".join(blocks_text)

        if download_dir is not None:
            target_dir = download_dir
        else:
            td = tempfile.TemporaryDirectory(prefix="quantumrag_notion_")
            self._temp_dirs.append(td)
            target_dir = Path(td.name)
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / f"{page_id}.md"
        file_path.write_text(content, encoding="utf-8")

        return file_path

    async def sync(
        self,
        last_sync: datetime | None = None,
    ) -> SyncResult:
        """Sync pages from a Notion database."""
        result = SyncResult()
        try:
            docs = await self.list_documents()
            for doc in docs:
                if last_sync is None or (doc.modified_at and doc.modified_at > last_sync):
                    result.added += 1
        except Exception as e:
            result.errors.append(str(e))

        return result


def _extract_title(page: dict[str, Any]) -> str:
    """Extract title from a Notion page object."""
    props = page.get("properties", {})
    for prop in props.values():
        if prop.get("type") == "title":
            title_parts = prop.get("title", [])
            return "".join(t.get("plain_text", "") for t in title_parts)
    return page.get("id", "Untitled")


def _block_to_text(block: dict[str, Any]) -> str:
    """Convert a Notion block to plain text."""
    block_type = block.get("type", "")
    block_data = block.get(block_type, {})

    if "rich_text" in block_data:
        parts = block_data["rich_text"]
        text = "".join(p.get("plain_text", "") for p in parts)

        if block_type.startswith("heading_1"):
            return f"# {text}"
        if block_type.startswith("heading_2"):
            return f"## {text}"
        if block_type.startswith("heading_3"):
            return f"### {text}"
        if block_type == "bulleted_list_item":
            return f"- {text}"
        if block_type == "numbered_list_item":
            return f"1. {text}"
        if block_type == "to_do":
            checked = block_data.get("checked", False)
            marker = "[x]" if checked else "[ ]"
            return f"- {marker} {text}"
        if block_type == "code":
            lang = block_data.get("language", "")
            return f"```{lang}\n{text}\n```"
        return text

    return ""
