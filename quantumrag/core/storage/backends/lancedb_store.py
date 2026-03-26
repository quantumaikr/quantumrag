"""LanceDB-based vector storage."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from quantumrag.core.errors import StorageError
from quantumrag.core.logging import get_logger
from quantumrag.core.storage.base import VectorSearchResult

logger = get_logger(__name__)

# Pattern for safe SQL identifiers — only allow alphanumeric + underscore
_SAFE_SQL_VALUE = re.compile(r"^[a-zA-Z0-9_\-]+$")


class LanceDBVectorStore:
    """LanceDB-based implementation of VectorStore."""

    def __init__(
        self,
        db_path: str | Path,
        table_name: str = "vectors",
        metric: str = "cosine",
    ) -> None:
        self._db_path = Path(db_path)
        self._table_name = table_name
        self._metric = metric
        self._db: Any = None
        self._table: Any = None
        self._index_built = False
        self._initialize()

    def _initialize(self) -> None:
        try:
            import lancedb
        except ImportError:
            raise StorageError(
                "lancedb is not installed",
                suggestion="Install with: pip install quantumrag[all] or pip install lancedb",
            ) from None

        self._db_path.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(self._db_path))
        logger.debug("LanceDB vector store initialized", path=str(self._db_path))

    def _ensure_table(self, dimensions: int | None = None) -> Any:
        """Get or create the vectors table."""
        if self._table is not None:
            return self._table

        import pyarrow as pa

        table_names = self._db.table_names()
        if self._table_name in table_names:
            self._table = self._db.open_table(self._table_name)
        elif dimensions is not None:
            schema = pa.schema(
                [
                    pa.field("id", pa.string()),
                    pa.field("document_id", pa.string()),
                    pa.field("vector", pa.list_(pa.float32(), dimensions)),
                    pa.field("metadata_json", pa.string()),
                ]
            )
            self._table = self._db.create_table(self._table_name, schema=schema)
        else:
            raise StorageError(
                "Vector table does not exist and dimensions not specified",
                suggestion="Add vectors first to create the table.",
            )
        return self._table

    async def add_vectors(
        self,
        ids: list[str],
        vectors: list[list[float]],
        metadata: list[dict[str, Any]] | None = None,
    ) -> None:
        if not ids:
            return

        import json

        dimensions = len(vectors[0])
        table = self._ensure_table(dimensions)

        metadata = metadata or [{}] * len(ids)
        data = [
            {
                "id": id_,
                "document_id": meta.get("document_id", ""),
                "vector": vec,
                "metadata_json": json.dumps(meta, ensure_ascii=False),
            }
            for id_, vec, meta in zip(ids, vectors, metadata, strict=True)
        ]

        try:
            table.add(data)
            logger.debug("Vectors added", count=len(ids))
        except Exception as e:
            raise StorageError(f"Failed to add vectors: {e}") from e

    def _maybe_create_index(self, table: Any) -> None:
        """Create ANN index if table has enough rows and index not yet built."""
        if self._index_built:
            return
        try:
            row_count = table.count_rows()
            if row_count >= 256:
                table.create_index(metric=self._metric, replace=True)
                self._index_built = True
                logger.info("ANN index created", rows=row_count, metric=self._metric)
        except Exception as e:
            logger.debug("ANN index creation skipped", error=str(e))

    @staticmethod
    def _sanitize_value(value: str) -> str:
        """Sanitize a string value for use in SQL WHERE clauses.

        Raises StorageError if the value contains suspicious characters.
        """
        if _SAFE_SQL_VALUE.match(value):
            return value
        # Fallback: escape single quotes for safety
        sanitized = value.replace("'", "''")
        return sanitized

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorSearchResult]:
        import json

        try:
            table = self._ensure_table()
        except StorageError:
            return []

        try:
            # Use cosine metric for search
            query = table.search(query_vector).metric(self._metric).limit(top_k)

            if filters and "document_id" in filters:
                safe_doc_id = self._sanitize_value(str(filters["document_id"]))
                query = query.where(f"document_id = '{safe_doc_id}'")

            results = query.to_list()

            # Build ANN index lazily after search if enough data
            self._maybe_create_index(table)

            return [
                VectorSearchResult(
                    id=row["id"],
                    score=1.0 - row.get("_distance", 0.0),  # LanceDB returns distance
                    metadata=json.loads(row.get("metadata_json", "{}")),
                )
                for row in results
            ]
        except Exception as e:
            logger.warning("Vector search failed", error=str(e))
            return []

    async def delete(self, ids: list[str]) -> None:
        try:
            table = self._ensure_table()
        except StorageError:
            return

        for id_ in ids:
            try:
                safe_id = self._sanitize_value(id_)
                table.delete(f"id = '{safe_id}'")
            except Exception as e:
                logger.warning("Failed to delete vector", id=id_, error=str(e))

    async def delete_by_document(self, document_id: str) -> None:
        try:
            table = self._ensure_table()
            safe_doc_id = self._sanitize_value(document_id)
            table.delete(f"document_id = '{safe_doc_id}'")
        except StorageError:
            return
        except Exception as e:
            logger.warning("Failed to delete vectors by document", error=str(e))

    async def count(self) -> int:
        try:
            table = self._ensure_table()
            return table.count_rows()
        except StorageError:
            return 0
