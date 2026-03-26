"""Local embedding provider using sentence-transformers.

Supports models like BAAI/bge-m3 that run on CPU without an API key.
Ideal for Korean-first self-hosted deployments.
"""

from __future__ import annotations

import asyncio
from typing import Any

from quantumrag.core.errors import StorageError
from quantumrag.core.logging import get_logger

logger = get_logger("quantumrag.llm.local_embedding")


class LocalEmbeddingProvider:
    """Embedding provider using a local sentence-transformers model.

    Lazy-loads the model on first use to avoid startup cost.
    Uses ``asyncio.to_thread`` to avoid blocking the event loop.

    Args:
        model: HuggingFace model name (default: BAAI/bge-m3).
        dimensions: Output dimensions. If the model supports Matryoshka
            truncation, embeddings are truncated to this size.
        device: Device to run on ('cpu', 'cuda', 'mps').
            Defaults to 'cpu' for broadest compatibility.
        batch_size: Batch size for encoding multiple texts.
    """

    def __init__(
        self,
        model: str = "BAAI/bge-m3",
        dimensions: int = 1024,
        device: str = "cpu",
        batch_size: int = 32,
    ) -> None:
        self._model_name = model
        self._dimensions = dimensions
        self._device = device
        self._batch_size = batch_size
        self._model: Any = None

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(
                self._model_name,
                device=self._device,
            )
            logger.info(
                "local_embedding_loaded",
                model=self._model_name,
                device=self._device,
            )
        except ImportError:
            raise StorageError(
                "sentence-transformers is not installed",
                suggestion="pip install sentence-transformers",
            ) from None

        return self._model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts, returning vectors."""
        model = self._ensure_model()

        def _encode() -> list[list[float]]:
            embeddings = model.encode(
                texts,
                batch_size=self._batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            # Truncate to requested dimensions (Matryoshka)
            truncated = embeddings[:, : self._dimensions]
            return truncated.tolist()

        return await asyncio.to_thread(_encode)

    async def embed_query(self, query: str) -> list[float]:
        """Embed a single query string."""
        results = await self.embed([query])
        return results[0]
