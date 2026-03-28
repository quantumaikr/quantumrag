"""ChromaDB-based vector storage.

ChromaDB is a popular open-source embedding database that supports
persistent storage, metadata filtering, and multiple distance metrics.

Install: ``pip install quantumrag[chroma]`` or ``pip install chromadb``
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantumrag.core.errors import StorageError
from quantumrag.core.logging import get_logger
from quantumrag.core.storage.base import VectorSearchResult

logger = get_logger(__name__)


class ChromaVectorStore:
    """ChromaDB-based implementation of VectorStore protocol."""

    def __init__(
        self,
        db_path: str | Path,
        collection_name: str = "vectors",
        metric: str = "cosine",
    ) -> None:
        self._db_path = Path(db_path)
        self._collection_name = collection_name
        self._metric = metric
        self._client: Any = None
        self._collection: Any = None
        self._initialize()

    def _initialize(self) -> None:
        try:
            import chromadb
        except ImportError:
            raise StorageError(
                "chromadb is not installed",
                suggestion="Install with: pip install quantumrag[chroma] or pip install chromadb",
            ) from None

        self._db_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self._db_path))
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": self._metric},
        )
        logger.debug("ChromaDB vector store initialized", path=str(self._db_path))

    async def add_vectors(
        self,
        ids: list[str],
        vectors: list[list[float]],
        metadata: list[dict[str, Any]] | None = None,
    ) -> None:
        if not ids:
            return

        metadata = metadata or [{}] * len(ids)

        # ChromaDB requires metadata values to be str, int, float, or bool.
        # Serialize complex metadata as a JSON string under a reserved key.
        chroma_meta = []
        for meta in metadata:
            flat: dict[str, Any] = {}
            flat["document_id"] = meta.get("document_id", "")
            flat["_raw"] = json.dumps(meta, ensure_ascii=False)
            chroma_meta.append(flat)

        try:
            self._collection.upsert(
                ids=ids,
                embeddings=vectors,
                metadatas=chroma_meta,
            )
            logger.debug("Vectors added to ChromaDB", count=len(ids))
        except Exception as e:
            raise StorageError(f"Failed to add vectors to ChromaDB: {e}") from e

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorSearchResult]:
        try:
            where = None
            if filters and "document_id" in filters:
                where = {"document_id": {"$eq": str(filters["document_id"])}}

            results = self._collection.query(
                query_embeddings=[query_vector],
                n_results=top_k,
                where=where,
                include=["metadatas", "distances"],
            )
        except Exception as e:
            logger.warning("ChromaDB search failed", error=str(e))
            return []

        search_results: list[VectorSearchResult] = []
        if not results["ids"] or not results["ids"][0]:
            return search_results

        ids = results["ids"][0]
        distances = results["distances"][0] if results["distances"] else [0.0] * len(ids)
        metadatas = results["metadatas"][0] if results["metadatas"] else [{}] * len(ids)

        for id_, distance, meta in zip(ids, distances, metadatas):
            # ChromaDB returns distance; convert to similarity score.
            # For cosine: similarity = 1 - distance
            score = max(0.0, 1.0 - distance)
            raw_meta = json.loads(meta.get("_raw", "{}")) if meta else {}
            search_results.append(VectorSearchResult(id=id_, score=score, metadata=raw_meta))

        return search_results

    async def delete(self, ids: list[str]) -> None:
        if not ids:
            return
        try:
            self._collection.delete(ids=ids)
        except Exception as e:
            logger.warning("Failed to delete from ChromaDB", error=str(e))

    async def delete_by_document(self, document_id: str) -> None:
        try:
            self._collection.delete(where={"document_id": {"$eq": document_id}})
        except Exception as e:
            logger.warning("Failed to delete by document from ChromaDB", error=str(e))

    async def count(self) -> int:
        try:
            return self._collection.count()
        except Exception:
            return 0
