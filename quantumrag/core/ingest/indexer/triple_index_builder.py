"""Triple Index Builder — builds Original Embedding + HyPE Embedding + Contextual BM25 indexes.

This is the heart of QuantumRAG's "Index-Heavy, Query-Light" philosophy.
All expensive computation happens here at indexing time, not at query time.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from quantumrag.core.logging import get_logger
from quantumrag.core.models import Chunk

logger = get_logger("quantumrag.indexer")


def _generate_fact_terms(chunk: Chunk) -> str:
    """Generate searchable terms from extracted facts (Level 2 → BM25 synergy).

    For example, a security fact with severity=Critical generates
    "Critical 보안 이슈" so it's findable by security-related queries.
    """
    facts = chunk.metadata.get("facts")
    if not facts:
        return ""

    terms: list[str] = []
    for fact in facts:
        ftype = fact.get("type", "")
        entity = fact.get("entity", "")

        if ftype == "security_issue":
            severity = fact.get("severity", "")
            status = fact.get("status", "")
            if entity:
                terms.append(f"{entity} 보안 이슈")
            if severity:
                terms.append(f"{severity} 보안 이슈")
                terms.append(f"{severity} 등급 보안")
            if status:
                terms.append(f"{status} 보안 이슈")
                terms.append(f"조치 {status}")

        elif ftype == "patent":
            if entity:
                terms.append(f"{entity} 특허")
            patent_status = fact.get("status", "")
            if patent_status:
                terms.append(f"{patent_status} 특허")
            inventors = fact.get("inventors", [])
            for inv in inventors:
                terms.append(f"{inv} 발명 특허")

        elif ftype == "customer_contract":
            customer = fact.get("customer", "")
            tier = fact.get("tier", "")
            deployment = fact.get("deployment", "")
            if customer and tier:
                terms.append(f"{customer} {tier} 고객")
            if deployment:
                terms.append(f"{deployment} 배포 고객")

        elif ftype == "product_version":
            version = fact.get("version", "")
            if version:
                terms.append(f"{version} 릴리스")

        elif ftype == "fund_allocation":
            item = fact.get("item", "")
            value = fact.get("value", "")
            if item and value:
                terms.append(f"{item} {value}원")
                terms.append(f"투자금 사용 용도 {item}")
                terms.append(f"자금 용도 {item}")

    return " ".join(terms)


# Default prompt for HyPE question generation
_HYPE_SYSTEM_PROMPT = """You are a question generation assistant. Given a text chunk from a document, generate hypothetical questions that this chunk would answer.
Output ONLY a JSON array of question strings, nothing else."""

_HYPE_USER_TEMPLATE = """Generate {n} diverse, specific questions that the following text would answer.
Questions should cover: key concepts, technical terms, named entities, numerical data, and relationships.
If the text is in Korean, generate Korean questions. If in English, generate English questions.
{context}
Text:
{text}

Output a JSON array of {n} question strings:"""


class TripleIndexBuilder:
    """Builds all three indexes for a set of chunks.

    The three indexes:
    1. Original Embedding: embed chunk text directly
    2. HyPE Embedding: generate hypothetical questions per chunk, embed those
    3. Contextual BM25: prepend context prefix to chunk text, index with BM25
    """

    def __init__(
        self,
        vector_store: Any,  # VectorStore
        hype_vector_store: Any,  # VectorStore (separate for HyPE)
        bm25_store: Any,  # BM25Store
        embedding_provider: Any,  # EmbeddingProvider
        llm_provider: Any | None = None,  # LLMProvider for HyPE generation
        hype_questions_per_chunk: int = 3,
        enable_hype: bool = True,
        max_concurrency: int = 5,
    ) -> None:
        self._vector_store = vector_store
        self._hype_vector_store = hype_vector_store
        self._bm25_store = bm25_store
        self._embedding_provider = embedding_provider
        self._llm_provider = llm_provider
        self._hype_n = hype_questions_per_chunk
        self._enable_hype = enable_hype and llm_provider is not None
        self._max_concurrency = max_concurrency

    async def build(
        self,
        chunks: list[Chunk],
        on_progress: Any | None = None,
    ) -> IndexingReport:
        """Build all three indexes for the given chunks."""
        report = IndexingReport()

        if not chunks:
            return report

        # Run original embedding and BM25 in parallel, then HyPE
        tasks = [
            self._build_original_embeddings(chunks, report),
            self._build_contextual_bm25(chunks, report),
        ]

        if self._enable_hype:
            tasks.append(self._build_hype_embeddings(chunks, report))

        await asyncio.gather(*tasks)

        report.total_chunks = len(chunks)
        logger.info(
            "triple_index_built",
            chunks=report.total_chunks,
            original_vectors=report.original_vectors,
            hype_vectors=report.hype_vectors,
            bm25_docs=report.bm25_documents,
        )
        return report

    async def _build_original_embeddings(self, chunks: list[Chunk], report: IndexingReport) -> None:
        """Build the original embedding index."""
        texts = [c.content for c in chunks]
        ids = [c.id for c in chunks]
        metadata = [{"document_id": c.document_id, "chunk_index": c.chunk_index} for c in chunks]

        try:
            vectors = await self._embedding_provider.embed(texts)
            await self._vector_store.add_vectors(ids, vectors, metadata)
            report.original_vectors = len(vectors)
        except Exception as e:
            logger.error("original_embedding_failed", error=str(e))
            report.errors.append(f"Original embedding: {e}")

    async def _build_hype_embeddings(self, chunks: list[Chunk], report: IndexingReport) -> None:
        """Build the HyPE embedding index — generate questions per chunk, then embed."""
        if not self._llm_provider:
            return

        all_questions: list[str] = []
        all_ids: list[str] = []
        all_metadata: list[dict[str, Any]] = []
        hype_failures = 0

        # Concurrent HyPE generation with semaphore to bound LLM calls
        semaphore = asyncio.Semaphore(self._max_concurrency)
        results: list[tuple[Chunk, list[str]]] = []

        async def _gen_one(chunk: Chunk) -> tuple[Chunk, list[str]]:
            async with semaphore:
                qs = await self._generate_hype_questions_with_retry(chunk)
                return (chunk, qs)

        tasks = [_gen_one(c) for c in chunks]
        results = await asyncio.gather(*tasks)

        for chunk, questions in results:
            if questions:
                chunk.hype_questions = questions
                for i, q in enumerate(questions):
                    q_id = f"{chunk.id}_hype_{i}"
                    all_questions.append(q)
                    all_ids.append(q_id)
                    all_metadata.append(
                        {
                            "document_id": chunk.document_id,
                            "chunk_id": chunk.id,
                            "chunk_index": chunk.chunk_index,
                            "question_index": i,
                        }
                    )
            else:
                hype_failures += 1
                report.errors.append(f"HyPE for chunk {chunk.id}: all retries failed")

        # Track HyPE coverage
        total = len(chunks)
        succeeded = total - hype_failures
        report.hype_coverage_ratio = succeeded / total if total > 0 else 0.0

        # Warn if more than 20% of chunks failed
        if total > 0 and (hype_failures / total) > 0.20:
            logger.warning(
                "hype_failure_threshold_exceeded",
                total_chunks=total,
                failed_chunks=hype_failures,
                coverage_ratio=report.hype_coverage_ratio,
            )

        if all_questions:
            try:
                vectors = await self._embedding_provider.embed(all_questions)
                await self._hype_vector_store.add_vectors(all_ids, vectors, all_metadata)
                report.hype_vectors = len(vectors)
            except Exception as e:
                logger.error("hype_embedding_failed", error=str(e))
                report.errors.append(f"HyPE embedding: {e}")

    async def _build_contextual_bm25(self, chunks: list[Chunk], report: IndexingReport) -> None:
        """Build the contextual BM25 index with derived term enrichment."""
        from quantumrag.core.ingest.indexer.derived_index import generate_derived_terms

        ids = [c.id for c in chunks]
        # Prepend context prefix + append derived terms to each chunk's text
        texts = []
        for c in chunks:
            base = f"{c.context_prefix} {c.content}" if c.context_prefix else c.content
            derived = generate_derived_terms(c.content)
            # Also generate terms from extracted facts (Level 2 → Level 3 synergy)
            fact_terms = _generate_fact_terms(c)
            all_derived = " ".join(filter(None, [derived, fact_terms]))
            texts.append(f"{base} {all_derived}" if all_derived else base)

        metadata = [{"document_id": c.document_id, "chunk_index": c.chunk_index} for c in chunks]

        try:
            await self._bm25_store.add_documents(ids, texts, metadata)
            report.bm25_documents = len(ids)
        except Exception as e:
            logger.error("bm25_indexing_failed", error=str(e))
            report.errors.append(f"BM25 indexing: {e}")

    async def _generate_hype_questions_with_retry(
        self, chunk: Chunk, max_retries: int = 2
    ) -> list[str]:
        """Generate HyPE questions with retry logic (exponential backoff: 1s, 2s).

        Retries when the result is empty (which indicates an internal failure
        that was caught by ``_generate_hype_questions``).
        """
        for attempt in range(max_retries + 1):
            try:
                questions = await self._generate_hype_questions(chunk)
                if questions:
                    return questions
                # Empty result is treated as a soft failure worth retrying
                if attempt < max_retries:
                    delay = 2**attempt  # 1s, 2s
                    logger.warning(
                        "hype_generation_retry",
                        chunk_id=chunk.id,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        delay=delay,
                        error="empty result",
                    )
                    await asyncio.sleep(delay)
            except Exception as e:
                if attempt < max_retries:
                    delay = 2**attempt  # 1s, 2s
                    logger.warning(
                        "hype_generation_retry",
                        chunk_id=chunk.id,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        delay=delay,
                        error=str(e),
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.warning(
                        "hype_generation_failed",
                        chunk_id=chunk.id,
                        error=str(e),
                    )
        return []

    async def _generate_hype_questions(self, chunk: Chunk) -> list[str]:
        """Generate hypothetical questions for a chunk using LLM."""
        # Adaptive question count: larger chunks get more questions
        n = self._hype_n
        content_len = len(chunk.content)
        if content_len > 1500:
            n = max(n, 5)
        elif content_len > 800:
            n = max(n, 4)

        # Build context from chunk metadata (section, document title)
        context_parts: list[str] = []
        meta = chunk.metadata or {}
        if meta.get("title"):
            context_parts.append(f"Document: {meta['title']}")
        if meta.get("breadcrumb"):
            context_parts.append(f"Section: {meta['breadcrumb']}")
        elif meta.get("section"):
            context_parts.append(f"Section: {meta['section']}")
        context = "\n".join(context_parts)
        if context:
            context = f"\nDocument context:\n{context}\n"

        # Use full content (no truncation) — LLM handles long inputs
        text = chunk.content[:4000] if content_len > 4000 else chunk.content
        prompt = _HYPE_USER_TEMPLATE.format(n=n, text=text, context=context)

        try:
            result = await self._llm_provider.generate_structured(  # type: ignore[union-attr]
                prompt,
                system=_HYPE_SYSTEM_PROMPT,
            )
            # Result should be a dict with a list, or just a list
            if isinstance(result, dict):
                questions = result.get("questions", list(result.values())[0] if result else [])
            elif isinstance(result, list):
                questions = result
            else:
                questions = []

            return [str(q) for q in questions[:n]]
        except Exception as e:
            # Fallback: try plain text generation and parse JSON
            logger.debug("hype_structured_failed", chunk_id=chunk.id, error=str(e))
            try:
                response = await self._llm_provider.generate(prompt, system=_HYPE_SYSTEM_PROMPT)  # type: ignore[union-attr]
                questions = json.loads(response.text)
                if isinstance(questions, list):
                    return [str(q) for q in questions[:n]]
            except (json.JSONDecodeError, Exception) as fallback_err:
                logger.warning(
                    "hype_generation_failed",
                    chunk_id=chunk.id,
                    error=str(fallback_err),
                    content_preview=chunk.content[:80],
                )
            return []


class IndexingReport:
    """Report of an indexing operation."""

    def __init__(self) -> None:
        self.total_chunks: int = 0
        self.original_vectors: int = 0
        self.hype_vectors: int = 0
        self.bm25_documents: int = 0
        self.errors: list[str] = []
        self.cost_usd: float = 0.0
        self.hype_coverage_ratio: float = 1.0

    @property
    def success(self) -> bool:
        return self.total_chunks > 0 and not self.errors
