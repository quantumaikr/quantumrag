"""Local embedding provider using sentence-transformers.

Supports models like microsoft/harrier-oss-v1-0.6b and BAAI/bge-m3
that run on CPU without an API key.
"""

from __future__ import annotations

import asyncio
from typing import Any

from quantumrag.core.errors import StorageError
from quantumrag.core.logging import get_logger

logger = get_logger("quantumrag.llm.local_embedding")

# Models that require query instructions for optimal retrieval
_INSTRUCTION_MODELS = {
    "microsoft/harrier-oss-v1-0.6b": "web_search_query",
    "microsoft/harrier-oss-v1-270m": "web_search_query",
    "microsoft/harrier-oss-v1-27b": "web_search_query",
}


class LocalEmbeddingProvider:
    """Embedding provider using a local sentence-transformers model.

    Lazy-loads the model on first use to avoid startup cost.
    Uses ``asyncio.to_thread`` to avoid blocking the event loop.

    Supports instruction-based models (e.g. Harrier) where queries
    need a task prompt but documents do not.

    Args:
        model: HuggingFace model name.
        dimensions: Output dimensions. Truncated via Matryoshka if supported.
        device: Device to run on ('cpu', 'cuda', 'mps').
        batch_size: Batch size for encoding multiple texts.
    """

    def __init__(
        self,
        model: str = "microsoft/harrier-oss-v1-270m",
        dimensions: int = 640,
        device: str = "cpu",
        batch_size: int = 32,
    ) -> None:
        self._model_name = model
        self._dimensions = dimensions
        self._device = device
        self._batch_size = batch_size
        self._model: Any = None
        self._query_prompt = _INSTRUCTION_MODELS.get(model)

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
                model_kwargs={"torch_dtype": "auto"},
            )
            logger.info(
                "local_embedding_loaded",
                model=self._model_name,
                device=self._device,
                dimensions=self._dimensions,
            )
        except ImportError:
            raise StorageError(
                "sentence-transformers is not installed",
                suggestion="pip install sentence-transformers",
            ) from None

        return self._model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed documents (no query instruction)."""
        model = self._ensure_model()

        def _encode() -> list[list[float]]:
            embeddings = model.encode(
                texts,
                batch_size=self._batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            truncated = embeddings[:, : self._dimensions]
            return truncated.tolist()

        return await asyncio.to_thread(_encode)

    async def embed_query(self, query: str) -> list[float]:
        """Embed a single query with instruction prompt if model requires it."""
        model = self._ensure_model()

        def _encode_query() -> list[float]:
            kwargs: dict[str, Any] = {
                "normalize_embeddings": True,
                "show_progress_bar": False,
            }
            if self._query_prompt:
                kwargs["prompt_name"] = self._query_prompt

            embedding = model.encode([query], **kwargs)
            truncated = embedding[:, : self._dimensions]
            return truncated[0].tolist()

        return await asyncio.to_thread(_encode_query)
