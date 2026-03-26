"""SQLite-based document and chunk storage."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from quantumrag.core.errors import StorageError
from quantumrag.core.logging import get_logger
from quantumrag.core.models import Chunk, Document, DocumentMetadata

logger = get_logger(__name__)

_SAFE_KEY_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")


def _validate_filter_key(key: str) -> str:
    """Validate that a filter key is safe for use in json_extract SQL expressions."""
    if not _SAFE_KEY_PATTERN.match(key):
        raise ValueError(f"Invalid filter key: {key!r}")
    return key


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    tables_json TEXT NOT NULL DEFAULT '[]',
    images_json TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    context_prefix TEXT NOT NULL DEFAULT '',
    hype_questions_json TEXT NOT NULL DEFAULT '[]',
    parent_chunk_id TEXT,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_chunk_index ON chunks(document_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_documents_source_id ON documents(
    json_extract(metadata_json, '$.source_id')
);
"""


class SQLiteDocumentStore:
    """SQLite-based implementation of DocumentStore."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._initialize()

    def _initialize(self) -> None:
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.commit()
        logger.debug("SQLite document store initialized", path=str(self._db_path))

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise StorageError("Database connection is closed")
        return self._conn

    async def add_document(self, document: Document) -> str:
        conn = self._get_conn()
        try:
            metadata_json = document.metadata.model_dump_json()
            tables_json = json.dumps(
                [t.model_dump(mode="json") for t in document.tables], ensure_ascii=False
            )
            images_json = json.dumps(
                [
                    {"caption": img.caption, "mime_type": img.mime_type, "page": img.page}
                    for img in document.images
                ],
                ensure_ascii=False,
            )
            conn.execute(
                "INSERT OR REPLACE INTO documents (id, content, metadata_json, tables_json, images_json) VALUES (?, ?, ?, ?, ?)",
                (document.id, document.content, metadata_json, tables_json, images_json),
            )
            conn.commit()
            logger.debug("Document stored", document_id=document.id)
            return document.id
        except sqlite3.Error as e:
            raise StorageError(f"Failed to store document: {e}") from e

    async def get_document(self, document_id: str) -> Document | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT id, content, metadata_json, tables_json, images_json FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_document(row)

    async def list_documents(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Document]:
        conn = self._get_conn()
        query = "SELECT id, content, metadata_json, tables_json, images_json FROM documents"
        params: list[Any] = []

        if filters:
            conditions = []
            for key, value in filters.items():
                _validate_filter_key(key)
                conditions.append(f"json_extract(metadata_json, '$.{key}') = ?")
                params.append(value)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, params).fetchall()
        return [self._row_to_document(row) for row in rows]

    async def delete_document(self, document_id: str) -> bool:
        conn = self._get_conn()
        # Chunks are deleted via CASCADE
        cursor = conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.debug("Document deleted", document_id=document_id)
        return deleted

    async def update_document(self, document: Document) -> bool:
        conn = self._get_conn()
        metadata_json = document.metadata.model_dump_json()
        cursor = conn.execute(
            "UPDATE documents SET content = ?, metadata_json = ? WHERE id = ?",
            (document.content, metadata_json, document.id),
        )
        conn.commit()
        return cursor.rowcount > 0

    async def add_chunks(self, chunks: list[Chunk]) -> list[str]:
        conn = self._get_conn()
        try:
            conn.executemany(
                "INSERT OR REPLACE INTO chunks (id, document_id, chunk_index, content, metadata_json, context_prefix, hype_questions_json, parent_chunk_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        chunk.id,
                        chunk.document_id,
                        chunk.chunk_index,
                        chunk.content,
                        json.dumps(chunk.metadata, ensure_ascii=False),
                        chunk.context_prefix,
                        json.dumps(chunk.hype_questions, ensure_ascii=False),
                        chunk.parent_chunk_id,
                    )
                    for chunk in chunks
                ],
            )
            conn.commit()
            logger.debug("Chunks stored", count=len(chunks))
            return [chunk.id for chunk in chunks]
        except sqlite3.Error as e:
            raise StorageError(f"Failed to store chunks: {e}") from e

    async def get_chunks(self, document_id: str) -> list[Chunk]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id, document_id, chunk_index, content, metadata_json, context_prefix, hype_questions_json, parent_chunk_id FROM chunks WHERE document_id = ? ORDER BY chunk_index",
            (document_id,),
        ).fetchall()
        return [self._row_to_chunk(row) for row in rows]

    async def get_chunk(self, chunk_id: str) -> Chunk | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT id, document_id, chunk_index, content, metadata_json, context_prefix, hype_questions_json, parent_chunk_id FROM chunks WHERE id = ?",
            (chunk_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_chunk(row)

    async def get_chunks_batch(self, chunk_ids: list[str]) -> dict[str, Chunk]:
        """Retrieve multiple chunks by their IDs in a single query.

        Returns a mapping of chunk_id → Chunk for all found chunks.
        """
        if not chunk_ids:
            return {}
        conn = self._get_conn()
        placeholders = ",".join("?" for _ in chunk_ids)
        rows = conn.execute(
            f"SELECT id, document_id, chunk_index, content, metadata_json, context_prefix, hype_questions_json, parent_chunk_id FROM chunks WHERE id IN ({placeholders})",
            chunk_ids,
        ).fetchall()
        return {row[0]: self._row_to_chunk(row) for row in rows}

    async def get_all_chunks(self, limit: int = 1000) -> list[Chunk]:
        """Retrieve all chunks (up to limit), ordered by document and index.

        Used by the evaluation pipeline to generate synthetic QA pairs.
        """
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id, document_id, chunk_index, content, metadata_json, context_prefix, hype_questions_json, parent_chunk_id FROM chunks ORDER BY document_id, chunk_index LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_chunk(row) for row in rows]

    async def count_documents(self) -> int:
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) FROM documents").fetchone()
        return row[0] if row else 0

    async def count_chunks(self) -> int:
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
        return row[0] if row else 0

    async def document_exists(self, source_id: str) -> bool:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT 1 FROM documents WHERE json_extract(metadata_json, '$.source_id') = ? LIMIT 1",
            (source_id,),
        ).fetchone()
        return row is not None

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @staticmethod
    def _row_to_document(row: tuple[Any, ...]) -> Document:
        doc_id, content, metadata_json, _tables_json, _images_json = row
        metadata = DocumentMetadata.model_validate_json(metadata_json)
        return Document(
            id=doc_id,
            content=content,
            metadata=metadata,
            tables=[],  # Simplified: full table reconstruction available if needed
            images=[],
        )

    @staticmethod
    def _row_to_chunk(row: tuple[Any, ...]) -> Chunk:
        (
            chunk_id,
            document_id,
            chunk_index,
            content,
            metadata_json,
            context_prefix,
            hype_questions_json,
            parent_chunk_id,
        ) = row
        return Chunk(
            id=chunk_id,
            document_id=document_id,
            chunk_index=chunk_index,
            content=content,
            metadata=json.loads(metadata_json),
            context_prefix=context_prefix,
            hype_questions=json.loads(hype_questions_json),
            parent_chunk_id=parent_chunk_id,
        )
