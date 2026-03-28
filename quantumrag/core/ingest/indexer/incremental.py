"""Incremental indexing - only process changed documents."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quantumrag.core.logging import get_logger

logger = get_logger("quantumrag.incremental")


@dataclass
class ChangeSet:
    """Set of changes detected between filesystem and index."""

    added: list[Path] = field(default_factory=list)
    modified: list[Path] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)  # document IDs

    @property
    def total_changes(self) -> int:
        return len(self.added) + len(self.modified) + len(self.deleted)

    @property
    def is_empty(self) -> bool:
        return self.total_changes == 0


@dataclass
class IncrementalResult:
    """Result of an incremental indexing operation."""

    added: int = 0
    updated: int = 0
    deleted: int = 0
    skipped: int = 0
    elapsed_seconds: float = 0.0


# Common document extensions
_DOC_EXTENSIONS = {
    ".txt",
    ".md",
    ".pdf",
    ".docx",
    ".doc",
    ".xlsx",
    ".xls",
    ".pptx",
    ".ppt",
    ".html",
    ".htm",
    ".csv",
    ".json",
    ".hwp",
    ".hwpx",
}


class IncrementalIndexer:
    """Track document changes and only re-index what changed.

    Uses content hashing to detect modifications and compares
    against the document store to find additions and deletions.
    """

    def __init__(self, document_store: Any) -> None:
        self._store = document_store

    async def detect_changes(
        self,
        path: Path,
        recursive: bool = True,
    ) -> ChangeSet:
        """Compare current files against indexed documents.

        Args:
            path: Directory or file path to scan.
            recursive: Whether to scan subdirectories.

        Returns:
            ChangeSet with added, modified, and deleted items.
        """
        changes = ChangeSet()

        # Collect current files
        if path.is_file():
            current_files = [path]
        elif path.is_dir():
            if recursive:
                current_files = [
                    f
                    for f in path.rglob("*")
                    if f.is_file() and f.suffix.lower() in _DOC_EXTENSIONS
                ]
            else:
                current_files = [
                    f for f in path.iterdir() if f.is_file() and f.suffix.lower() in _DOC_EXTENSIONS
                ]
        else:
            return changes

        # Get indexed documents
        indexed_docs = await self._store.list_documents(limit=10000)
        indexed_by_source: dict[str, Any] = {}
        for doc in indexed_docs:
            source_id = doc.metadata.source_id if hasattr(doc.metadata, "source_id") else doc.id
            indexed_by_source[source_id] = doc

        # Compare
        current_source_ids: set[str] = set()
        for file_path in current_files:
            source_id = str(file_path)
            current_source_ids.add(source_id)

            if source_id not in indexed_by_source:
                changes.added.append(file_path)
            else:
                # Check if content has changed via hash
                doc = indexed_by_source[source_id]
                current_hash = _file_hash(file_path)
                stored_hash = (
                    doc.metadata.custom.get("content_hash", "")
                    if hasattr(doc.metadata, "custom")
                    else ""
                )
                if current_hash != stored_hash:
                    changes.modified.append(file_path)

        # Find deleted documents (in index but not on filesystem)
        for source_id, doc in indexed_by_source.items():
            if source_id not in current_source_ids:
                changes.deleted.append(doc.id)

        logger.info(
            "changes_detected",
            added=len(changes.added),
            modified=len(changes.modified),
            deleted=len(changes.deleted),
        )

        return changes

    async def apply_changes(
        self,
        changes: ChangeSet,
        indexer: Any,
    ) -> IncrementalResult:
        """Apply only the changes (add new, update modified, remove deleted).

        Args:
            changes: The detected change set.
            indexer: An indexer instance with ingest_file() and delete_document() methods.

        Returns:
            IncrementalResult with counts.
        """
        t0 = time.perf_counter()
        result = IncrementalResult()

        if changes.is_empty:
            result.elapsed_seconds = time.perf_counter() - t0
            return result

        # Add new files
        for file_path in changes.added:
            try:
                await indexer.ingest_file(
                    file_path, extra_metadata={"content_hash": _file_hash(file_path)}
                )
                result.added += 1
            except Exception:
                logger.warning("add_failed", path=str(file_path), exc_info=True)
                result.skipped += 1

        # Update modified files (delete old + re-add)
        for file_path in changes.modified:
            try:
                source_id = str(file_path)
                # Try to find and delete existing document
                docs = await self._store.list_documents(filters={"source_id": source_id}, limit=1)
                for doc in docs:
                    await self._store.delete_document(doc.id)

                await indexer.ingest_file(
                    file_path, extra_metadata={"content_hash": _file_hash(file_path)}
                )
                result.updated += 1
            except Exception:
                logger.warning("update_failed", path=str(file_path), exc_info=True)
                result.skipped += 1

        # Delete removed documents
        for doc_id in changes.deleted:
            try:
                await self._store.delete_document(doc_id)
                result.deleted += 1
            except Exception:
                logger.warning("delete_failed", doc_id=doc_id, exc_info=True)
                result.skipped += 1

        result.elapsed_seconds = time.perf_counter() - t0
        logger.info(
            "incremental_indexing_complete",
            added=result.added,
            updated=result.updated,
            deleted=result.deleted,
            skipped=result.skipped,
            elapsed=f"{result.elapsed_seconds:.2f}s",
        )

        return result


def _file_hash(path: Path, block_size: int = 65536) -> str:
    """Compute SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            data = f.read(block_size)
            if not data:
                break
            hasher.update(data)
    return hasher.hexdigest()
