"""Reranking module for improving retrieval precision."""

from __future__ import annotations

import os
from typing import Any, Protocol, runtime_checkable

from quantumrag.core.logging import get_logger
from quantumrag.core.retrieve.fusion import ScoredChunk

logger = get_logger("quantumrag.reranker")


@runtime_checkable
class Reranker(Protocol):
    """Protocol for reranking retrieved chunks."""

    async def rerank(
        self, query: str, chunks: list[ScoredChunk], top_k: int = 5
    ) -> list[ScoredChunk]:
        """Rerank chunks by relevance to query."""
        ...


class FlashRankReranker:
    """Free CPU-based reranker using FlashRank.

    FlashRank is fast, free, and runs locally on CPU.
    Perfect default for most use cases.
    """

    def __init__(self, model_name: str = "ms-marco-MiniLM-L-12-v2") -> None:
        self._model_name = model_name
        self._ranker: Any = None

    def _ensure_ranker(self) -> Any:
        if self._ranker is not None:
            return self._ranker

        try:
            from flashrank import Ranker, RerankRequest  # noqa: F401

            self._ranker = Ranker(model_name=self._model_name)
        except ImportError:
            logger.warning("flashrank not installed, reranking disabled")
            self._ranker = None
        return self._ranker

    async def rerank(
        self, query: str, chunks: list[ScoredChunk], top_k: int = 5
    ) -> list[ScoredChunk]:
        ranker = self._ensure_ranker()
        if ranker is None:
            return chunks[:top_k]

        try:
            from flashrank import RerankRequest

            passages = [{"id": str(i), "text": sc.chunk.content} for i, sc in enumerate(chunks)]
            request = RerankRequest(query=query, passages=passages)
            results = ranker.rerank(request)

            # Map back to ScoredChunks with new scores
            reranked = []
            for result in results[:top_k]:
                idx = int(result["id"])
                original = chunks[idx]
                reranked.append(ScoredChunk(chunk=original.chunk, score=result["score"]))

            logger.debug("reranked", query_len=len(query), input=len(chunks), output=len(reranked))
            return reranked
        except Exception as e:
            logger.warning("reranking_failed", error=str(e))
            return chunks[:top_k]


class CohereReranker:
    """Reranker using the Cohere Rerank API.

    Requires the ``cohere`` package (lazy-imported) and an API key
    provided either directly or via the ``COHERE_API_KEY`` env var.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "rerank-v3.5",
    ) -> None:
        self._api_key = api_key or os.environ.get("COHERE_API_KEY", "")
        self._model = model
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client

        try:
            import cohere

            self._client = cohere.ClientV2(api_key=self._api_key)
        except ImportError:
            logger.warning("cohere not installed, reranking disabled")
            self._client = None
        return self._client

    async def rerank(
        self, query: str, chunks: list[ScoredChunk], top_k: int = 5
    ) -> list[ScoredChunk]:
        client = self._ensure_client()
        if client is None:
            return chunks[:top_k]

        try:
            documents = [sc.chunk.content for sc in chunks]
            response = client.rerank(
                query=query,
                documents=documents,
                top_n=top_k,
                model=self._model,
            )

            reranked: list[ScoredChunk] = []
            for result in response.results:
                idx = result.index
                reranked.append(
                    ScoredChunk(chunk=chunks[idx].chunk, score=result.relevance_score)
                )

            logger.debug("cohere_reranked", query_len=len(query), input=len(chunks), output=len(reranked))
            return reranked
        except Exception as e:
            logger.warning("cohere_reranking_failed", error=str(e))
            return chunks[:top_k]


class JinaReranker:
    """Reranker using the Jina Rerank API via HTTP.

    Uses ``httpx`` for HTTP calls (lazy-imported). API key is read from
    the ``JINA_API_KEY`` environment variable or passed directly.
    """

    JINA_RERANK_URL = "https://api.jina.ai/v1/rerank"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "jina-reranker-v2-base-multilingual",
    ) -> None:
        self._api_key = api_key or os.environ.get("JINA_API_KEY", "")
        self._model = model

    async def rerank(
        self, query: str, chunks: list[ScoredChunk], top_k: int = 5
    ) -> list[ScoredChunk]:
        try:
            import httpx
        except ImportError:
            logger.warning("httpx not installed, reranking disabled")
            return chunks[:top_k]

        try:
            payload = {
                "query": query,
                "documents": [sc.chunk.content for sc in chunks],
                "top_n": top_k,
                "model": self._model,
            }
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self.JINA_RERANK_URL,
                    json=payload,
                    headers=headers,
                    timeout=30.0,
                )
                resp.raise_for_status()
                data = resp.json()

            reranked: list[ScoredChunk] = []
            for result in data["results"]:
                idx = result["index"]
                reranked.append(
                    ScoredChunk(
                        chunk=chunks[idx].chunk,
                        score=result["relevance_score"],
                    )
                )

            logger.debug("jina_reranked", query_len=len(query), input=len(chunks), output=len(reranked))
            return reranked
        except Exception as e:
            logger.warning("jina_reranking_failed", error=str(e))
            return chunks[:top_k]


class BGEReranker:
    """Cross-encoder reranker using BAAI/bge-reranker-v2-m3.

    Open-source, multilingual (including Korean), runs locally.
    Requires ``sentence-transformers`` package.  The model is lazy-loaded
    on first use (~600 MB download on first run).

    Falls back to top-k truncation if the package is not installed.
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3") -> None:
        self._model_name = model_name
        self._model: Any = None

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self._model_name)
            logger.info("bge_reranker_loaded", model=self._model_name)
        except ImportError:
            logger.warning(
                "sentence-transformers not installed, BGE reranking disabled",
                suggestion="pip install sentence-transformers",
            )
            self._model = None
        return self._model

    async def rerank(
        self, query: str, chunks: list[ScoredChunk], top_k: int = 5
    ) -> list[ScoredChunk]:
        model = self._ensure_model()
        if model is None:
            return chunks[:top_k]

        try:
            import asyncio

            pairs = [[query, sc.chunk.content] for sc in chunks]
            # CrossEncoder.predict is blocking — run in thread pool
            scores = await asyncio.to_thread(model.predict, pairs)

            indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
            reranked = [
                ScoredChunk(chunk=chunks[idx].chunk, score=float(score))
                for idx, score in indexed[:top_k]
            ]

            logger.debug("bge_reranked", query_len=len(query), input=len(chunks), output=len(reranked))
            return reranked
        except Exception as e:
            logger.warning("bge_reranking_failed", error=str(e))
            return chunks[:top_k]


class NoopReranker:
    """Pass-through reranker that does nothing (for when reranking is disabled)."""

    async def rerank(
        self, query: str, chunks: list[ScoredChunk], top_k: int = 5
    ) -> list[ScoredChunk]:
        return chunks[:top_k]


def create_reranker(provider: str, **kwargs: Any) -> Reranker:
    """Factory function for creating a reranker by provider name.

    Args:
        provider: One of "flashrank", "bge", "cohere", "jina", or "noop".
        **kwargs: Extra keyword arguments forwarded to the reranker constructor.

    Returns:
        A :class:`Reranker`-compatible instance.
    """
    providers: dict[str, type] = {
        "flashrank": FlashRankReranker,
        "bge": BGEReranker,
        "cohere": CohereReranker,
        "jina": JinaReranker,
        "noop": NoopReranker,
    }

    cls = providers.get(provider)
    if cls is None:
        logger.warning("unknown_reranker_provider", provider=provider, fallback="noop")
        return NoopReranker()

    return cls(**kwargs)  # type: ignore[return-value]
