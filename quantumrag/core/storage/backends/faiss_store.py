"""FAISS-based vector storage.

FAISS (Facebook AI Similarity Search) is the industry-standard library
for efficient similarity search of dense vectors.

Install: ``pip install quantumrag[faiss]`` or ``pip install faiss-cpu``
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantumrag.core.errors import StorageError
from quantumrag.core.logging import get_logger
from quantumrag.core.storage.base import VectorSearchResult

logger = get_logger(__name__)


class FAISSVectorStore:
    """FAISS-based implementation of VectorStore protocol.

    Uses an IndexFlatIP (inner-product / cosine on normalized vectors)
    for exact search, and persists the index + metadata to disk.
    """

    def __init__(
        self,
        db_path: str | Path,
        metric: str = "cosine",
    ) -> None:
        self._db_path = Path(db_path)
        self._metric = metric
        self._faiss: Any = None
        self._np: Any = None
        self._index: Any = None
        self._dimensions: int | None = None
        # Parallel arrays: position i in FAISS index <-> _ids[i] / _metadata[i]
        self._ids: list[str] = []
        self._metadata: list[dict[str, Any]] = []
        self._initialize()

    def _initialize(self) -> None:
        try:
            import faiss
            import numpy as np
        except ImportError:
            raise StorageError(
                "faiss-cpu is not installed",
                suggestion="Install with: pip install quantumrag[faiss] or pip install faiss-cpu",
            ) from None

        self._faiss = faiss
        self._np = np
        self._db_path.mkdir(parents=True, exist_ok=True)
        self._load_if_exists()
        logger.debug("FAISS vector store initialized", path=str(self._db_path))

    # -- persistence helpers ------------------------------------------------

    @property
    def _index_file(self) -> Path:
        return self._db_path / "faiss.index"

    @property
    def _meta_file(self) -> Path:
        return self._db_path / "faiss_meta.json"

    def _load_if_exists(self) -> None:
        if self._index_file.exists() and self._meta_file.exists():
            try:
                self._index = self._faiss.read_index(str(self._index_file))
                self._dimensions = self._index.d
                with open(self._meta_file) as f:
                    data = json.load(f)
                self._ids = data["ids"]
                self._metadata = data["metadata"]
                logger.debug("FAISS index loaded", vectors=len(self._ids))
            except Exception as e:
                logger.warning("Failed to load FAISS index, starting fresh", error=str(e))
                self._index = None
                self._ids = []
                self._metadata = []

    def _save(self) -> None:
        if self._index is None:
            return
        try:
            self._faiss.write_index(self._index, str(self._index_file))
            with open(self._meta_file, "w") as f:
                json.dump({"ids": self._ids, "metadata": self._metadata}, f, ensure_ascii=False)
        except Exception as e:
            logger.warning("Failed to save FAISS index", error=str(e))

    def _ensure_index(self, dimensions: int) -> Any:
        if self._index is not None:
            return self._index

        self._dimensions = dimensions
        # Use inner product on L2-normalized vectors = cosine similarity
        self._index = self._faiss.IndexFlatIP(dimensions)
        return self._index

    def _normalize(self, vectors: Any) -> Any:
        """L2-normalize vectors so inner product = cosine similarity."""
        norms = self._np.linalg.norm(vectors, axis=1, keepdims=True)
        norms = self._np.maximum(norms, 1e-10)
        return vectors / norms

    # -- VectorStore protocol -----------------------------------------------

    async def add_vectors(
        self,
        ids: list[str],
        vectors: list[list[float]],
        metadata: list[dict[str, Any]] | None = None,
    ) -> None:
        if not ids:
            return

        np = self._np
        dimensions = len(vectors[0])
        index = self._ensure_index(dimensions)
        metadata = metadata or [{}] * len(ids)

        arr = np.array(vectors, dtype=np.float32)
        arr = self._normalize(arr)

        # Handle upsert: remove existing IDs first
        existing_positions = {id_: i for i, id_ in enumerate(self._ids)}
        positions_to_remove = []
        for id_ in ids:
            if id_ in existing_positions:
                positions_to_remove.append(existing_positions[id_])

        if positions_to_remove:
            self._rebuild_without(positions_to_remove)

        index.add(arr)
        self._ids.extend(ids)
        self._metadata.extend(metadata)
        self._save()

        logger.debug("Vectors added to FAISS", count=len(ids))

    def _rebuild_without(self, positions: list[int]) -> None:
        """Rebuild FAISS index excluding given positions."""
        np = self._np
        if self._index is None or not self._ids:
            return

        remove_set = set(positions)
        total = self._index.ntotal
        if total == 0:
            return

        all_vectors = self._faiss.rev_swig_ptr(
            self._index.get_xb(),
            total * self._dimensions,  # type: ignore[union-attr]
        )
        all_vectors = np.array(all_vectors, dtype=np.float32).reshape(total, self._dimensions)  # type: ignore[union-attr]

        keep_mask = [i not in remove_set for i in range(total)]
        kept_vectors = all_vectors[keep_mask]

        new_index = self._faiss.IndexFlatIP(self._dimensions)  # type: ignore[arg-type]
        if len(kept_vectors) > 0:
            new_index.add(kept_vectors)

        self._ids = [id_ for i, id_ in enumerate(self._ids) if i not in remove_set]
        self._metadata = [m for i, m in enumerate(self._metadata) if i not in remove_set]
        self._index = new_index

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorSearchResult]:
        if self._index is None or self._index.ntotal == 0:
            return []

        np = self._np
        query = np.array([query_vector], dtype=np.float32)
        query = self._normalize(query)

        # Fetch more candidates if we need to filter
        fetch_k = min(top_k * 4, self._index.ntotal) if filters else min(top_k, self._index.ntotal)

        try:
            scores, indices = self._index.search(query, fetch_k)
        except Exception as e:
            logger.warning("FAISS search failed", error=str(e))
            return []

        results: list[VectorSearchResult] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:  # FAISS returns -1 for missing
                continue
            idx = int(idx)
            if idx >= len(self._ids):
                continue

            meta = self._metadata[idx] if idx < len(self._metadata) else {}

            # Apply filter
            if (
                filters
                and "document_id" in filters
                and meta.get("document_id") != str(filters["document_id"])
            ):
                continue

            results.append(
                VectorSearchResult(
                    id=self._ids[idx],
                    score=float(max(0.0, score)),  # IP score on normalized = cosine sim
                    metadata=meta,
                )
            )
            if len(results) >= top_k:
                break

        return results

    async def delete(self, ids: list[str]) -> None:
        if not ids or not self._ids:
            return

        id_set = set(ids)
        positions = [i for i, id_ in enumerate(self._ids) if id_ in id_set]
        if positions:
            self._rebuild_without(positions)
            self._save()

    async def delete_by_document(self, document_id: str) -> None:
        if not self._ids:
            return

        positions = [
            i for i, meta in enumerate(self._metadata) if meta.get("document_id") == document_id
        ]
        if positions:
            self._rebuild_without(positions)
            self._save()

    async def count(self) -> int:
        if self._index is None:
            return 0
        return self._index.ntotal
