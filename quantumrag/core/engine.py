"""Engine — the single entry point for all QuantumRAG functionality.

Usage:
    from quantumrag import Engine

    engine = Engine()
    engine.ingest("./docs")
    result = engine.query("What is the revenue?")
    print(result.answer)
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import re
import time
from collections.abc import AsyncIterator, Coroutine
from pathlib import Path
from typing import Any, TypeVar

from quantumrag.core.config import QuantumRAGConfig
from quantumrag.core.generate.router import QueryClassification, QueryRouter
from quantumrag.core.logging import get_logger, setup_logging
from quantumrag.core.models import Confidence, EvalResult, QueryComplexity, QueryResult, TraceStep
from quantumrag.core.pipeline.context import DocumentProfile, PipelineContext

_T = TypeVar("_T")


def _run_sync(coro: Coroutine[Any, Any, _T]) -> _T:
    """Run an async coroutine from synchronous code.

    Handles three environments:
    1. No running loop (standalone script): use ``asyncio.run()`` directly.
    2. Running loop (FastAPI, Jupyter): offload to a new thread with its own loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — safe to use asyncio.run()
        return asyncio.run(coro)

    # A loop is already running (e.g. FastAPI, Jupyter) — run in a thread
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


logger = get_logger("quantumrag.engine")

# Patterns that need broader retrieval to capture all relevant items
_BROAD_RETRIEVAL_PATTERNS = [
    # Superlative + financial terms
    re.compile(
        r"(?:가장|제일|최대|최소|최고|최저)\s*.{0,10}(?:계약|규모|금액|매출|비용|PoC|투자|예산|팀)"
    ),
    re.compile(r"(?:계약|규모|금액|매출|비용|PoC|투자).{0,10}(?:가장|제일|최대|최소)"),
    # Cross-verification queries — need multiple sources to compare
    re.compile(r"(?:일치|다른|차이|불일치|동일|같은가|다른가)"),
    # Multi-constraint filtering — need broad coverage
    re.compile(r"(?:온프레미스|클라우드).{0,15}(?:Enterprise|Pro|고객|배포)"),
    # Conditional reasoning — need related context
    re.compile(r"(?:충분|부족|가능|달성).{0,10}(?:한가|할까|인가|일까)"),
    # Derived calculations needing multiple data points
    re.compile(r"1인당|팀별|고객사당|연평균|성장률|CAGR|비중"),
    # Temporal range queries — need all items in period
    re.compile(r"(?:상반기|하반기|분기|월\s*이후|월\s*이전|년\s*(?:이후|이전|사이))"),
    # Severity/grade filtering — need all items at or above threshold
    re.compile(r"(?:등급|레벨|수준)\s*.{0,6}(?:이상|이하|초과|미만)"),
    # Enumeration — "모두 나열/열거/알려" needs broad coverage but not Map-Reduce
    re.compile(r"(?:모두|전부|모든).*(?:나열|열거|알려|말해)"),
    # Explicit listing requests — "나열하세요", "열거하세요"
    re.compile(r"(?:나열|열거)\s*(?:하세요|해주세요|해\s*줘)"),
    # Counterfactual/conditional with specific numbers — need source data
    re.compile(r"(?:실패|성사|성공|전환).*(?:하면|할\s*경우|시)"),
]


def _needs_broad_retrieval(query: str) -> bool:
    """Detect if a query needs broader retrieval for comparison/cross-check."""
    return any(p.search(query) for p in _BROAD_RETRIEVAL_PATTERNS)


# FDO Fix P3: Input sanitization patterns
_MALICIOUS_INPUT_PATTERNS = [
    re.compile(r"(?i)SELECT\s+.+\s+FROM\s+"),
    re.compile(r"(?i)DROP\s+TABLE"),
    re.compile(r"(?i)INSERT\s+INTO"),
    re.compile(r"(?i)DELETE\s+FROM"),
    re.compile(r"(?i)UPDATE\s+.+\s+SET"),
    re.compile(r"(?i)UNION\s+SELECT"),
    re.compile(r"<script[^>]*>", re.IGNORECASE),
    re.compile(r"javascript:", re.IGNORECASE),
    re.compile(r"(?i)(?:ignore|disregard)\s+(?:previous|above|all)\s+(?:instructions|prompts)"),
    re.compile(r";\s*(?:DROP|DELETE|INSERT|UPDATE)\s", re.IGNORECASE),
    # Korean prompt injection patterns
    re.compile(r"(?:이전|위의?|모든)\s*(?:지시|명령|프롬프트|지침)를?\s*(?:무시|잊어|취소)"),
    re.compile(r"시스템\s*프롬프트를?\s*(?:출력|보여|알려)"),
]


def _is_malicious_input(query: str) -> bool:
    """Detect SQL injection, XSS, prompt injection attempts."""
    return any(p.search(query) for p in _MALICIOUS_INPUT_PATTERNS)


class Engine:
    """QuantumRAG Engine — Put in docs, ask questions, it just works.

    This is the single entry point for all QuantumRAG functionality.
    """

    def __init__(
        self,
        config: str | Path | QuantumRAGConfig | None = None,
        *,
        document_store: Any | None = None,
        vector_store: Any | None = None,
        bm25_store: Any | None = None,
        embedding_model: str | None = None,
        generation_model: str | None = None,
        data_dir: str | None = None,
    ) -> None:
        # Load config — auto-detect provider when no config given
        if isinstance(config, QuantumRAGConfig):
            self._config = config
        elif isinstance(config, (str, Path)):
            self._config = QuantumRAGConfig.from_yaml(config)
        else:
            self._config = QuantumRAGConfig.auto()

        # Apply overrides
        if embedding_model:
            self._config.models.embedding.model = embedding_model
        if generation_model:
            self._config.models.generation.medium.model = generation_model
        if data_dir:
            self._config.storage.data_dir = data_dir

        setup_logging()
        self._initialized = False
        self._components: dict[str, Any] = {}
        self._router = QueryRouter()

        # Chunk Constellation Graph — built at ingest time, used at query time
        self._chunk_graph: Any = None
        self._entity_index: Any = None
        self._fact_index: Any = None  # Fact-First RAG: structured fact index

        # Document profiles — built at ingest time, used at query time
        self._document_profiles: dict[str, DocumentProfile] = {}

        # Cached retriever instance — avoid recreating per query (major speed win)
        self._cached_retriever: Any = None
        self._cached_fusion: Any = None

        # Accept pre-built storage instances (useful for testing / DI)
        if document_store is not None:
            self._components["document_store"] = document_store
        if vector_store is not None:
            self._components["vector_store_original"] = vector_store
        if bm25_store is not None:
            self._components["bm25_store"] = bm25_store

    def _ensure_initialized(self) -> None:
        """Lazy initialization of all components."""
        if self._initialized:
            return

        data_dir = Path(self._config.storage.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)

        # Initialize document store via factory if not already provided
        if "document_store" not in self._components:
            from quantumrag.core.storage.factory import StorageFactory

            self._components["document_store"] = StorageFactory.create_document_store(
                backend="sqlite", db_path=data_dir / "documents.db"
            )

        # Vector stores and BM25 are initialized on first use
        # to avoid requiring lancedb/tantivy just for basic usage

        self._initialized = True
        logger.info("engine_initialized", data_dir=str(data_dir))

    def _get_document_store(self) -> Any:
        self._ensure_initialized()
        return self._components["document_store"]

    def _get_vector_store(self, name: str = "original") -> Any:
        key = f"vector_store_{name}"
        if key not in self._components:
            from quantumrag.core.storage.factory import StorageFactory

            data_dir = Path(self._config.storage.data_dir)
            self._components[key] = StorageFactory.create_vector_store(
                backend="lancedb",
                db_path=data_dir / f"vectors_{name}",
                table_name=name,
            )
        return self._components[key]

    def _get_bm25_store(self) -> Any:
        if "bm25_store" not in self._components:
            from quantumrag.core.storage.factory import StorageFactory
            from quantumrag.korean.morphology import KoreanTokenizer

            data_dir = Path(self._config.storage.data_dir)
            tokenizer = KoreanTokenizer() if self._config.language == "ko" else None
            self._components["bm25_store"] = StorageFactory.create_bm25_store(
                backend="tantivy", index_path=data_dir / "bm25_index", tokenizer=tokenizer
            )
        return self._components["bm25_store"]

    def _get_embedding_provider(self) -> Any:
        if "embedding_provider" not in self._components:
            cfg = self._config.models.embedding
            if cfg.provider == "openai":
                from quantumrag.core.llm.providers.openai import OpenAIEmbeddingProvider

                kwargs: dict[str, Any] = {"model": cfg.model, "dimensions": cfg.dimensions}
                if cfg.api_key:
                    kwargs["api_key"] = cfg.api_key
                if cfg.base_url:
                    kwargs["base_url"] = cfg.base_url
                self._components["embedding_provider"] = OpenAIEmbeddingProvider(**kwargs)
            elif cfg.provider == "gemini":
                from quantumrag.core.llm.providers.gemini import GeminiEmbeddingProvider

                kwargs = {"model": cfg.model}
                if cfg.api_key:
                    kwargs["api_key"] = cfg.api_key
                if cfg.dimensions:
                    kwargs["dimensions"] = cfg.dimensions
                self._components["embedding_provider"] = GeminiEmbeddingProvider(**kwargs)
            elif cfg.provider == "ollama":
                from quantumrag.core.llm.providers.ollama import OllamaEmbeddingProvider

                kwargs = {"model": cfg.model}
                if cfg.base_url:
                    kwargs["base_url"] = cfg.base_url
                self._components["embedding_provider"] = OllamaEmbeddingProvider(**kwargs)
            elif cfg.provider == "local":
                from quantumrag.core.llm.providers.local_embedding import LocalEmbeddingProvider

                kwargs = {"model": cfg.model, "dimensions": cfg.dimensions}
                self._components["embedding_provider"] = LocalEmbeddingProvider(**kwargs)
            else:
                from quantumrag.core.errors import ConfigError

                raise ConfigError(f"Unknown embedding provider: {cfg.provider}")
        return self._components["embedding_provider"]

    def _get_llm_provider(self, complexity: QueryComplexity = QueryComplexity.MEDIUM) -> Any:
        tier_map = {
            QueryComplexity.SIMPLE: self._config.models.generation.simple,
            QueryComplexity.MEDIUM: self._config.models.generation.medium,
            QueryComplexity.COMPLEX: self._config.models.generation.complex,
        }
        tier_cfg = tier_map[complexity]
        cache_key = f"llm_{tier_cfg.provider}_{tier_cfg.model}"

        if cache_key not in self._components:
            if tier_cfg.provider == "openai":
                from quantumrag.core.llm.providers.openai import OpenAILLMProvider

                kwargs: dict[str, Any] = {"model": tier_cfg.model}
                if tier_cfg.api_key:
                    kwargs["api_key"] = tier_cfg.api_key
                if tier_cfg.base_url:
                    kwargs["base_url"] = tier_cfg.base_url
                self._components[cache_key] = OpenAILLMProvider(**kwargs)
            elif tier_cfg.provider == "anthropic":
                from quantumrag.core.llm.providers.anthropic import AnthropicLLMProvider

                kwargs = {"model": tier_cfg.model}
                if tier_cfg.api_key:
                    kwargs["api_key"] = tier_cfg.api_key
                self._components[cache_key] = AnthropicLLMProvider(**kwargs)
            elif tier_cfg.provider == "gemini":
                from quantumrag.core.llm.providers.gemini import GeminiLLMProvider

                kwargs = {"model": tier_cfg.model}
                if tier_cfg.api_key:
                    kwargs["api_key"] = tier_cfg.api_key
                self._components[cache_key] = GeminiLLMProvider(**kwargs)
            elif tier_cfg.provider == "ollama":
                from quantumrag.core.llm.providers.ollama import OllamaLLMProvider

                kwargs = {"model": tier_cfg.model}
                if tier_cfg.base_url:
                    kwargs["base_url"] = tier_cfg.base_url
                self._components[cache_key] = OllamaLLMProvider(**kwargs)
            else:
                from quantumrag.core.errors import ConfigError

                raise ConfigError(f"Unknown LLM provider: {tier_cfg.provider}")
        return self._components[cache_key]

    # --- Public Accessors ---

    def get_document_store(self) -> Any:
        """Return the document store, initializing the engine if needed."""
        return self._get_document_store()

    # --- Public API ---

    def ingest(
        self,
        path: str | Path,
        *,
        chunking_strategy: str | None = None,
        metadata: dict[str, Any] | None = None,
        recursive: bool = True,
        enable_hype: bool = True,
        mode: str | None = None,
    ) -> IngestResult:
        """Ingest documents from a file, directory, or URL.

        Args:
            mode: Override ingest mode ("full", "fast", "minimal").
                  - full: all enrichment (HyPE, preambles, facts, quality, multi-res)
                  - fast: skip HyPE and preambles (quick indexing, still good retrieval)
                  - minimal: parse + chunk + embed + BM25 only (fastest)
        """
        return _run_sync(
            self.aingest(
                path,
                chunking_strategy=chunking_strategy,
                metadata=metadata,
                recursive=recursive,
                enable_hype=enable_hype,
                mode=mode,
            )
        )

    async def aingest(
        self,
        path: str | Path,
        *,
        chunking_strategy: str | None = None,
        metadata: dict[str, Any] | None = None,
        recursive: bool = True,
        enable_hype: bool = True,
        mode: str | None = None,
    ) -> IngestResult:
        """Async version of ingest.

        Modes:
            full:    All enrichment (HyPE, preambles, facts, quality, multi-res, entity index, chunk graph)
            fast:    Skip HyPE and contextual preambles (quick indexing, still good retrieval via embedding+BM25)
            minimal: Parse + chunk + embed + BM25 only (fastest possible, no LLM calls)
        """
        self._ensure_initialized()
        t0 = time.perf_counter()

        ingest_mode = mode or self._config.ingest.mode
        if ingest_mode not in ("full", "fast", "minimal"):
            from quantumrag.core.errors import ConfigError

            raise ConfigError(
                f"Unknown ingest mode: {ingest_mode!r}. Must be 'full', 'fast', or 'minimal'."
            )

        # Resolve mode flags
        do_hype = enable_hype and ingest_mode == "full"
        do_preamble = self._config.ingest.contextual_preamble and ingest_mode == "full"
        do_facts = ingest_mode in ("full", "fast")
        do_quality = self._config.ingest.quality_check and ingest_mode in ("full", "fast")
        do_multi_res = ingest_mode in ("full", "fast")
        do_entity_index = ingest_mode in ("full", "fast")
        do_chunk_graph = ingest_mode == "full"
        max_concurrency = self._config.ingest.max_concurrency
        parse_concurrency = self._config.ingest.parse_concurrency

        logger.info("ingest_start", mode=ingest_mode, path=str(path))

        # --- Pre-flight validation: catch fatal errors early ---
        errors: list[str] = []
        try:
            self._get_embedding_provider()
        except Exception as e:
            from quantumrag.core.errors import ConfigError

            raise ConfigError(f"Embedding provider initialization failed: {e}") from e

        if do_hype:
            try:
                self._get_llm_provider(QueryComplexity.SIMPLE)
            except Exception as e:
                logger.warning("preflight_llm_unavailable", error=str(e))
                errors.append(f"LLM provider unavailable — disabling HyPE and preambles: {e}")
                do_hype = False
                do_preamble = False

        path = Path(path) if not isinstance(path, Path) else path
        doc_store = self._get_document_store()

        # --- Phase 1: Parse documents (parallel) ---
        documents = await self._parse_documents(
            path,
            registry=None,
            metadata=metadata,
            recursive=recursive,
            errors=errors,
            parse_concurrency=parse_concurrency,
        )

        # Denoise parsed text (post-parse, pre-chunk cleaning)
        from quantumrag.core.ingest.denoiser import TextDenoiser

        denoiser = TextDenoiser()
        for doc in documents:
            doc.content = denoiser.denoise(doc.content)

        # --- Phase 2: Chunk, enrich, index per document ---
        from quantumrag.core.ingest.chunker.auto import AutoChunker

        override = chunking_strategy or self._config.ingest.chunking.strategy
        chunker = AutoChunker(
            chunk_size=self._config.ingest.chunking.chunk_size,
            overlap=self._config.ingest.chunking.overlap,
            override=override if override != "auto" else None,
        )

        from quantumrag.core.pipeline.profiler import DocumentProfiler

        profiler = DocumentProfiler()

        # --- Phase 2: Chunk + enrich per document, accumulate all chunks ---
        all_chunks: list[Any] = []
        total_chunks = 0
        for doc in documents:
            await doc_store.add_document(doc)

            # Profile document (Index-Heavy: compute once, use everywhere)
            try:
                doc_profile = profiler.profile(doc)
                self._document_profiles[doc.id] = doc_profile
            except Exception as e:
                logger.debug("document_profiling_skipped", error=str(e))
                doc_profile = None

            chunks = chunker.chunk(doc, document_profile=doc_profile)

            # Coherence gate: merge chunks with poor boundary quality
            try:
                from quantumrag.core.ingest.chunker.coherence import ChunkCoherenceGate

                coherence_gate = ChunkCoherenceGate()
                chunks = coherence_gate.refine(chunks)
            except Exception as e:
                logger.warning("coherence_gate_failed", error=str(e))

            # Contextual Retrieval: LLM-generated preambles (Anthropic-style)
            if do_preamble:
                try:
                    from quantumrag.core.ingest.chunker.context import generate_contextual_preambles

                    preamble_llm = self._get_llm_provider(QueryComplexity.SIMPLE)
                    chunks = await generate_contextual_preambles(
                        chunks,
                        doc,
                        preamble_llm,
                        max_concurrency=max_concurrency,
                    )
                except Exception as e:
                    logger.warning("contextual_preamble_failed", error=str(e))

            # Structured fact extraction — enrich chunks with domain-specific facts
            if do_facts:
                try:
                    from quantumrag.core.ingest.indexer.fact_extractor import (
                        extract_facts_for_chunks,
                    )

                    chunks = extract_facts_for_chunks(chunks)
                except Exception as e:
                    logger.warning("fact_extraction_failed", error=str(e))

            # Chunk quality filtering — remove broken/boilerplate chunks
            if do_quality:
                from quantumrag.core.ingest.quality import ChunkQualityChecker

                quality_checker = ChunkQualityChecker()
                chunks = quality_checker.filter_chunks(chunks)

            # Multi-resolution index: create document & section summary chunks
            if do_multi_res:
                try:
                    from quantumrag.core.ingest.indexer.multi_resolution import (
                        build_multi_resolution_chunks,
                    )

                    summary_chunks = build_multi_resolution_chunks(chunks, doc)
                    if summary_chunks:
                        chunks.extend(summary_chunks)
                except Exception as e:
                    logger.warning("multi_resolution_failed", error=str(e))

            await doc_store.add_chunks(chunks)
            total_chunks += len(chunks)
            all_chunks.extend(chunks)

        # --- Phase 3: Cross-document indexing (single batch) ---

        # Build Triple Index — one batch call across ALL documents
        if all_chunks:
            try:
                embedding_provider = self._get_embedding_provider()
                from quantumrag.core.ingest.indexer.triple_index_builder import TripleIndexBuilder

                hype_llm = None
                if do_hype:
                    with contextlib.suppress(Exception):
                        hype_llm = self._get_llm_provider(QueryComplexity.SIMPLE)

                builder = TripleIndexBuilder(
                    vector_store=self._get_vector_store("original"),
                    hype_vector_store=self._get_vector_store("hype") if do_hype else None,
                    bm25_store=self._get_bm25_store(),
                    embedding_provider=embedding_provider,
                    llm_provider=hype_llm if do_hype else None,
                    hype_questions_per_chunk=self._config.models.hype.questions_per_chunk
                    if do_hype
                    else 0,
                    max_concurrency=max_concurrency,
                )
                await builder.build(all_chunks)
            except Exception as e:
                logger.warning("indexing_partial_failure", error=str(e))

        # Build Entity Reverse Index — uses in-memory chunks, no re-fetch
        if do_entity_index and all_chunks:
            try:
                from quantumrag.core.ingest.indexer.entity_index import EntityIndex

                self._entity_index = EntityIndex()
                self._entity_index.build(all_chunks)
            except Exception as e:
                logger.warning("entity_index_build_failed", error=str(e))

        # Build Fact Index — structured fact store for Fact-First retrieval
        if do_facts and all_chunks:
            try:
                from quantumrag.core.retrieve.fact_index import FactIndex

                self._fact_index = FactIndex()
                self._fact_index.build_from_chunks(all_chunks)
            except Exception as e:
                logger.warning("fact_index_build_failed", error=str(e))

        # Build Chunk Constellation Graph — uses in-memory chunks, no re-fetch
        if do_chunk_graph and all_chunks:
            try:
                from quantumrag.core.ingest.indexer.chunk_graph import build_chunk_graph

                self._chunk_graph = build_chunk_graph(all_chunks)
                logger.info(
                    "chunk_graph_ready",
                    nodes=self._chunk_graph.node_count,
                    edges=self._chunk_graph.edge_count,
                )
            except Exception as e:
                logger.warning("chunk_graph_build_failed", error=str(e))

        elapsed = time.perf_counter() - t0
        result = IngestResult(
            documents=len(documents),
            chunks=total_chunks,
            elapsed_seconds=elapsed,
            errors=errors,
        )
        logger.info(
            "ingest_complete",
            mode=ingest_mode,
            documents=result.documents,
            chunks=result.chunks,
            elapsed=f"{elapsed:.1f}s",
        )
        return result

    async def _parse_documents(
        self,
        path: Path,
        *,
        registry: Any | None = None,
        metadata: dict[str, Any] | None = None,
        recursive: bool = True,
        errors: list[str],
        parse_concurrency: int = 4,
    ) -> list[Any]:
        """Parse documents with parallel I/O for directories."""
        from quantumrag.core.ingest.parser.base import create_default_registry

        if registry is None:
            registry = create_default_registry()

        documents: list[Any] = []

        if path.is_file():
            doc = await self._parse_single_file(path, registry, metadata, errors)
            if doc is not None:
                documents.append(doc)
        elif path.is_dir():
            files = sorted(
                f
                for f in (path.rglob("*") if recursive else path.glob("*"))
                if f.is_file() and registry.has_parser(f.suffix)
            )
            # Parse files concurrently with bounded parallelism
            semaphore = asyncio.Semaphore(parse_concurrency)

            async def _parse_one(fp: Path) -> Any | None:
                async with semaphore:
                    return await self._parse_single_file(fp, registry, metadata, errors)

            results = await asyncio.gather(*[_parse_one(f) for f in files])
            documents = [doc for doc in results if doc is not None]

        return documents

    async def _parse_single_file(
        self,
        file_path: Path,
        registry: Any,
        metadata: dict[str, Any] | None,
        errors: list[str],
    ) -> Any | None:
        """Parse a single file, returning Document or None on failure."""
        try:
            parser = registry.get_parser(file_path.suffix)
        except Exception as e:
            errors.append(f"{file_path.name}: {e}")
            logger.warning("no_parser", path=str(file_path), error=str(e))
            return None

        try:
            doc = await asyncio.to_thread(parser.parse, file_path)
            if metadata:
                doc.metadata.custom.update(metadata)
            if not doc.content.strip():
                errors.append(f"{file_path.name}: No text content extracted")
                logger.warning("empty_content", path=str(file_path))
                return None
            return doc
        except Exception as e:
            errors.append(f"{file_path.name}: {e}")
            logger.warning("parse_failed", path=str(file_path), error=str(e))
            return None

    def query(
        self,
        query: str,
        *,
        filters: dict[str, Any] | None = None,
        top_k: int | None = None,
        rerank: bool | None = None,
        conversation_history: list[Any] | None = None,
        skip_correction: bool = False,
    ) -> QueryResult:
        """Query the knowledge base."""
        return _run_sync(
            self.aquery(
                query,
                filters=filters,
                top_k=top_k,
                rerank=rerank,
                conversation_history=conversation_history,
                skip_correction=skip_correction,
            )
        )

    async def aquery(
        self,
        query: str,
        *,
        filters: dict[str, Any] | None = None,
        top_k: int | None = None,
        rerank: bool | None = None,
        conversation_history: list[Any] | None = None,
        skip_correction: bool = False,
    ) -> QueryResult:
        """Async query the knowledge base.

        Args:
            skip_correction: Skip post-generation correction pipeline.
                Faster but may reduce accuracy on complex queries.
        """
        self._ensure_initialized()
        t0 = time.perf_counter()
        trace: list[TraceStep] = []

        # Early return for empty queries
        if not query or not query.strip():
            return QueryResult(
                answer="질문을 입력해주세요."
                if self._config.language == "ko"
                else "Please enter a question.",
                confidence=Confidence.INSUFFICIENT_EVIDENCE,
                trace=trace,
            )

        # FDO Fix P3: Input sanitization — reject SQL/XSS/injection attempts
        if _is_malicious_input(query):
            logger.warning("malicious_input_detected", query=query[:80])
            return QueryResult(
                answer="유효하지 않은 입력입니다. 문서에 대한 질문을 입력해주세요."
                if self._config.language == "ko"
                else "Invalid input detected. Please enter a question about your documents.",
                confidence=Confidence.INSUFFICIENT_EVIDENCE,
                trace=[
                    TraceStep(
                        step="input_sanitization",
                        result="malicious input rejected",
                        latency_ms=0,
                    )
                ],
            )

        # Step 0: Rewrite query if conversation history is provided
        if conversation_history:
            from quantumrag.core.generate.rewriter import ConversationTurn, QueryRewriter

            # Convert plain dicts to ConversationTurn objects if needed
            turns: list[ConversationTurn] = []
            for item in conversation_history:
                if isinstance(item, ConversationTurn):
                    turns.append(item)
                elif isinstance(item, dict):
                    turns.append(ConversationTurn(role=item["role"], content=item["content"]))

            # Use LLM-based rewriting for high-quality pronoun resolution
            try:
                rewrite_llm = self._get_llm_provider(QueryComplexity.SIMPLE)
            except Exception:
                rewrite_llm = None
            rewriter = QueryRewriter(llm_provider=rewrite_llm)
            original_query = query
            query = await rewriter.rewrite(query, history=turns)

            # Strategy D: Topic Tracker — detect implicit topic continuity
            # If rewriter didn't change the query (no pronouns), check if
            # the conversation topic should still be injected
            if query == original_query:
                from quantumrag.core.generate.topic_tracker import (
                    augment_query_with_topic,
                    get_active_topic,
                )

                topic = get_active_topic(query, conversation_history)
                if topic:
                    query = augment_query_with_topic(query, topic)
                    trace.append(
                        TraceStep(
                            step="topic_augment",
                            result=query,
                            latency_ms=0,
                            details={"original": original_query, "topic": topic},
                        )
                    )

            if query != original_query:
                trace.append(
                    TraceStep(
                        step="rewrite",
                        result=query,
                        latency_ms=0,
                        details={"original": original_query},
                    )
                )

        # Step 0.5 + 0.7 + 1: Parallel preprocessing
        # Run query expansion (if needed) concurrently with classification + decomposition
        from quantumrag.core.generate.query_expander import QueryExpander, is_colloquial
        from quantumrag.core.generate.rewriter import decompose_query

        async def _maybe_expand(q: str) -> tuple[str, float]:
            if not is_colloquial(q):
                return q, 0.0
            try:
                expand_llm = self._get_llm_provider(QueryComplexity.SIMPLE)
                expander = QueryExpander(expand_llm)
                t_expand = time.perf_counter()
                expanded = await expander.expand(q)
                return expanded, (time.perf_counter() - t_expand) * 1000
            except Exception:
                return q, 0.0

        # Classification + decomposition are instant (no I/O), run alongside expansion
        expand_task = asyncio.create_task(_maybe_expand(query))
        classification = self._router.classify(query)
        sub_queries = decompose_query(query)

        expanded_query, expand_ms = await expand_task

        if expanded_query != query:
            trace.append(
                TraceStep(
                    step="query_expansion",
                    result=expanded_query,
                    latency_ms=expand_ms,
                    details={"original": query},
                )
            )
            query = expanded_query
            # Re-decompose with expanded query
            sub_queries = decompose_query(query)

        if len(sub_queries) > 1:
            trace.append(
                TraceStep(
                    step="decompose",
                    result=f"{len(sub_queries)} sub-queries",
                    latency_ms=0,
                    details={"sub_queries": sub_queries},
                )
            )

        trace.append(
            TraceStep(
                step="classify",
                result=f"{classification.complexity.value}/{classification.query_type}",
                latency_ms=0,
            )
        )

        # Build PipelineContext with enriched signals
        pipeline_ctx = PipelineContext(document_profiles=dict(self._document_profiles))
        try:
            from quantumrag.core.pipeline.signals import build_query_signal

            active_profiles = (
                list(self._document_profiles.values()) if self._document_profiles else None
            )
            query_signal = build_query_signal(
                query=query,
                complexity=classification.complexity.value,
                confidence=classification.confidence,
                needs_retrieval=classification.needs_retrieval,
                query_type=classification.query_type,
                active_profiles=active_profiles,
            )
            pipeline_ctx.query_signal = query_signal
            pipeline_ctx.active_domain = query_signal.domain
            pipeline_ctx.active_language = query_signal.language
            pipeline_ctx.merge_retrieval_hints(query_signal.retrieval_hints)
            pipeline_ctx.log_signal(
                "engine",
                "query_signal",
                domain=query_signal.domain.value,
                intent=query_signal.intent.value,
            )

            trace.append(
                TraceStep(
                    step="pipeline_signal",
                    result=f"domain={query_signal.domain.value} intent={query_signal.intent.value}",
                    latency_ms=0,
                    details={
                        "domain_confidence": query_signal.domain_confidence,
                        "output_format": query_signal.output_format,
                        "retrieval_hints": {
                            "top_k_multiplier": query_signal.retrieval_hints.top_k_multiplier,
                            "skip_compression": query_signal.retrieval_hints.skip_compression,
                            "prefer_bm25": query_signal.retrieval_hints.prefer_bm25,
                        },
                    },
                )
            )
        except Exception as e:
            logger.debug("query_signal_build_skipped", error=str(e))

        # Self-routing: skip retrieval if not needed
        if not classification.needs_retrieval:
            return QueryResult(
                answer="I can help with questions about your documents. Please ask a question about the content you've ingested.",
                confidence=Confidence.INSUFFICIENT_EVIDENCE,
                trace=trace,
            )

        top_k = top_k or self._config.retrieval.top_k

        # Adaptive retrieval depth: broader search for aggregation/complex queries
        from quantumrag.core.generate.map_reduce import needs_aggregation

        use_map_reduce = needs_aggregation(query)
        if use_map_reduce:
            top_k = max(top_k, 20)  # Aggregation needs broad coverage
        elif _needs_broad_retrieval(query):
            top_k = max(top_k, 12)  # Superlative/comparison/enumeration needs more candidates
        elif classification.complexity == QueryComplexity.COMPLEX:
            top_k = max(top_k, 8)

        # Boost top_k for large document collections (PDF-heavy, many chunks)
        if self._document_profiles:
            has_deep_docs = any(
                p.heading_depth >= 2 or p.paragraph_count > 30
                for p in self._document_profiles.values()
            )
            if has_deep_docs:
                top_k = max(top_k, 15)

        # Step 2: Retrieve (with sub-query fusion if decomposed)
        try:
            if len(sub_queries) > 1:
                # Parallel retrieval for each sub-query, then merge & deduplicate
                import asyncio as _aio

                sub_results = await _aio.gather(
                    *(
                        self._do_retrieval(sq, classification, top_k, filters, rerank, pipeline_ctx)
                        for sq in sub_queries
                    )
                )
                # Merge: use the first result as base, add unique chunks from others
                retrieval_result = sub_results[0]
                seen_ids = {sc.chunk.id for sc in retrieval_result.chunks}
                for sr in sub_results[1:]:
                    for sc in sr.chunks:
                        if sc.chunk.id not in seen_ids:
                            retrieval_result.chunks.append(sc)
                            seen_ids.add(sc.chunk.id)
                    retrieval_result.sources.extend(
                        s
                        for s in sr.sources
                        if s.chunk_id not in {src.chunk_id for src in retrieval_result.sources}
                    )
                    retrieval_result.trace.extend(sr.trace)
                # Re-sort by score, deduplicate, and trim
                retrieval_result.chunks.sort(key=lambda sc: sc.score, reverse=True)
                from quantumrag.core.retrieve.diversity import deduplicate_chunks

                retrieval_result.chunks = deduplicate_chunks(retrieval_result.chunks)
                retrieval_result.chunks = retrieval_result.chunks[: top_k * 2]
            else:
                retrieval_result = await self._do_retrieval(
                    query, classification, top_k, filters, rerank, pipeline_ctx
                )
            trace.extend(retrieval_result.trace)

            # Document coherence boost: if multiple chunks from the same
            # document appear, boost their scores (the document is likely relevant)
            try:
                retrieval_result.chunks = _apply_doc_coherence_boost(retrieval_result.chunks)
            except Exception:
                pass  # Non-critical optimization

        except Exception as e:
            logger.error("retrieval_failed", error=str(e))
            return QueryResult(
                answer=f"Retrieval failed: {e}",
                confidence=Confidence.INSUFFICIENT_EVIDENCE,
                trace=trace,
            )

        # Step 2.5a: Entity-based retrieval injection
        # If query has structured constraints (severity, status, entity IDs),
        # use the reverse index to inject guaranteed-recall chunks.
        if self._entity_index and retrieval_result.chunks:
            try:
                from quantumrag.core.retrieve.entity_detector import detect_entity_query

                entity_query = detect_entity_query(query)
                if entity_query and entity_query.has_constraints:
                    entity_chunk_ids = self._entity_index.lookup_combined(
                        entity_keys=entity_query.entity_ids or None,
                        attributes={"status": entity_query.status} if entity_query.status else None,
                        severity_gte=entity_query.severity_gte,
                    )
                    # Also inject fund allocation chunks if query asks about fund usage
                    if entity_query.fund_allocation:
                        fund_ids = self._entity_index.lookup("type:fund_allocation")
                        entity_chunk_ids = (
                            entity_chunk_ids | fund_ids if entity_chunk_ids else fund_ids
                        )
                    if entity_chunk_ids:
                        # Inject missing chunks OR replace compressed versions
                        seen_ids = {sc.chunk.id for sc in retrieval_result.chunks}
                        missing_ids = entity_chunk_ids - seen_ids
                        # Also replace any already-retrieved chunks with full versions
                        # (compression may have removed critical content)
                        replace_ids = entity_chunk_ids & seen_ids
                        all_needed_ids = missing_ids | replace_ids
                        if all_needed_ids:
                            doc_store = self._get_document_store()
                            full_chunks = await doc_store.get_chunks_batch(list(all_needed_ids))
                            from quantumrag.core.retrieve.fusion import ScoredChunk

                            # Replace compressed versions with full versions
                            if replace_ids:
                                for i, sc in enumerate(retrieval_result.chunks):
                                    if sc.chunk.id in replace_ids and sc.chunk.id in full_chunks:
                                        retrieval_result.chunks[i] = ScoredChunk(
                                            chunk=full_chunks[sc.chunk.id],
                                            score=max(sc.score, 0.8),
                                        )
                            # Inject missing chunks
                            for cid, chunk in full_chunks.items():
                                if cid in missing_ids:
                                    retrieval_result.chunks.append(
                                        ScoredChunk(chunk=chunk, score=0.8)
                                    )
                            trace.append(
                                TraceStep(
                                    step="entity_injection",
                                    result=f"injected {len(missing_ids)} new, replaced {len(replace_ids)} compressed",
                                    latency_ms=0,
                                )
                            )
            except Exception as e:
                logger.debug("entity_injection_skipped", error=str(e))

        # Step 2.5b: Map-Reduce for aggregation queries
        from quantumrag.core.generate.map_reduce import MapReduceRAG

        if use_map_reduce and retrieval_result.chunks:
            try:
                mr_llm = self._get_llm_provider(QueryComplexity.MEDIUM)
                mr_rag = MapReduceRAG(mr_llm)

                # For aggregation, use ALL retrieved chunks (broader is better)
                mr_chunks = retrieval_result.chunks

                t_mr = time.perf_counter()
                mr_answer = await mr_rag.execute(query, mr_chunks)
                mr_ms = (time.perf_counter() - t_mr) * 1000
                trace.append(
                    TraceStep(
                        step="map_reduce",
                        result=f"aggregated {len(mr_chunks)} chunks",
                        latency_ms=mr_ms,
                    )
                )

                total_ms = (time.perf_counter() - t0) * 1000
                return QueryResult(
                    answer=mr_answer,
                    sources=retrieval_result.sources,
                    confidence=Confidence.STRONGLY_SUPPORTED,
                    trace=trace,
                    metadata={"total_latency_ms": total_ms, "path": "map_reduce"},
                )
            except Exception as e:
                logger.warning("map_reduce_failed_fallback", error=str(e))
                # Fall through to standard generation

        # Step 2.7: Fact-First Injection — query the fact index directly
        # For structured queries (filtering, enumeration), inject verified facts
        # into a synthetic high-priority chunk so the LLM sees authoritative data.
        if self._fact_index and self._fact_index.total_facts > 0 and retrieval_result.chunks:
            try:
                from quantumrag.core.ingest.indexer.fact_extractor import detect_domains

                q_domains = detect_domains(query)
                fact_context = ""

                if "contract" in q_domains:
                    # Customer/contract queries: inject full customer list
                    customer_facts = self._fact_index.get_all_of_type("customer_contract")
                    if customer_facts:
                        fact_context = self._fact_index.format_facts_as_context(
                            customer_facts, label="검증된 고객 데이터 (전체 목록)"
                        )

                elif "finance" in q_domains:
                    finance_facts = self._fact_index.get_all_of_type("finance_metric")
                    fund_facts = self._fact_index.get_all_of_type("fund_allocation")
                    all_finance = finance_facts + fund_facts
                    if all_finance:
                        fact_context = self._fact_index.format_facts_as_context(
                            all_finance, label="검증된 재무 데이터"
                        )

                elif "security" in q_domains:
                    sec_facts = self._fact_index.get_all_of_type("security_issue")
                    if sec_facts:
                        fact_context = self._fact_index.format_facts_as_context(
                            sec_facts, label="검증된 보안 이슈 데이터"
                        )

                elif "hr" in q_domains:
                    hr_facts = self._fact_index.get_all_of_type(
                        "team_info"
                    ) + self._fact_index.get_all_of_type("team_leader")
                    if hr_facts:
                        fact_context = self._fact_index.format_facts_as_context(
                            hr_facts, label="검증된 조직 데이터"
                        )

                # Inject as a high-priority synthetic chunk at the front
                if fact_context:
                    from quantumrag.core.models import Chunk as FactChunk
                    from quantumrag.core.retrieve.fusion import ScoredChunk as FactSC

                    fact_chunk = FactChunk(
                        content=fact_context,
                        document_id="__fact_index__",
                        chunk_index=0,
                        metadata={"title": "Fact Index", "section": "구조화 데이터"},
                    )
                    # Score higher than all text chunks to appear first in context
                    top_score = retrieval_result.chunks[0].score if retrieval_result.chunks else 1.0
                    retrieval_result.chunks.insert(
                        0, FactSC(chunk=fact_chunk, score=top_score * 1.1)
                    )
                    trace.append(
                        TraceStep(
                            step="fact_first_injection",
                            result=f"injected {len(fact_context)} chars of verified facts",
                            latency_ms=0,
                            details={"domains": q_domains},
                        )
                    )
            except Exception as e:
                logger.debug("fact_first_injection_skipped", error=str(e))

        # Step 3: Generate
        try:
            llm = self._get_llm_provider(classification.complexity)
            from quantumrag.core.generate.generator import Generator

            generator = Generator(
                llm_provider=llm,
                language=self._config.language,
                temperature=self._config.generation.temperature,
                max_tokens=self._config.generation.max_tokens,
                high_confidence_threshold=self._config.generation.high_confidence_threshold,
                low_confidence_threshold=self._config.generation.low_confidence_threshold,
                no_answer_penalty=self._config.generation.no_answer_penalty,
                max_context_chars=self._config.generation.max_context_chars,
            )
            result = await generator.generate(
                query, retrieval_result.chunks, retrieval_result.sources
            )
            # Merge traces
            result.trace = trace + result.trace

            # Step 4: Post-generation correction pipeline
            # Modular chain: Retrieval Retry → Self-Correct → Fact Verify → Completeness
            if skip_correction:
                total_ms = (time.perf_counter() - t0) * 1000
                result.metadata["total_latency_ms"] = total_ms
                result.metadata["path"] = classification.complexity.value
                result.metadata["skip_correction"] = True
                return result

            from quantumrag.core.pipeline.postprocess import (
                CorrectionContext,
                CorrectionPipeline,
            )

            correction_ctx = CorrectionContext(
                query=query,
                result=result,
                chunks=retrieval_result.chunks,
                sources=retrieval_result.sources,
                classification=classification,
                top_k=top_k,
                filters=filters,
                rerank=rerank,
                pipeline_ctx=pipeline_ctx,
                generator=generator,
                retriever=self._make_retriever_adapter(classification, pipeline_ctx),
                trace=trace,
                use_map_reduce=use_map_reduce,
                config=self._config,
            )

            correction_ctx = await CorrectionPipeline().run(correction_ctx)
            result = correction_ctx.result

            total_ms = (time.perf_counter() - t0) * 1000
            result.metadata["total_latency_ms"] = total_ms
            result.metadata["path"] = classification.complexity.value

            return result
        except Exception as e:
            logger.error("generation_failed", error=str(e))
            return QueryResult(
                answer=f"Generation failed: {e}",
                sources=retrieval_result.sources,
                confidence=Confidence.INSUFFICIENT_EVIDENCE,
                trace=trace,
            )

    async def query_stream(
        self,
        query: str,
        *,
        filters: dict[str, Any] | None = None,
        top_k: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream query results token by token.

        Note: Streaming skips the post-generation correction pipeline
        (retrieval retry, self-correct, fact verification, completeness).
        For maximum accuracy, use ``query()`` instead.
        """
        self._ensure_initialized()
        classification = self._router.classify(query)
        top_k = top_k or self._config.retrieval.top_k

        retrieval_result = await self._do_retrieval(query, classification, top_k, filters)

        llm = self._get_llm_provider(classification.complexity)
        from quantumrag.core.generate.generator import Generator

        generator = Generator(llm_provider=llm, language=self._config.language)
        async for token in generator.generate_stream(query, retrieval_result.chunks):
            yield token

    def _make_retriever_adapter(
        self, classification: QueryClassification, pipeline_ctx: Any
    ) -> Any:
        """Create a retriever adapter that satisfies the PostProcessor protocol.

        Wraps _do_retrieval and _do_retrieval_retry into the simple
        interface expected by CorrectionContext.
        """
        return _EngineRetrieverAdapter(self)

    def _get_fusion_retriever(self) -> Any:
        """Get or create cached FusionRetriever — avoids per-query recreation."""
        if self._cached_fusion is None:
            from quantumrag.core.retrieve.fusion import FusionRetriever

            self._cached_fusion = FusionRetriever(
                vector_store=self._get_vector_store("original"),
                hype_vector_store=self._get_vector_store("hype"),
                bm25_store=self._get_bm25_store(),
                embedding_provider=self._get_embedding_provider(),
                document_store=self._get_document_store(),
                weights={
                    "original": self._config.retrieval.fusion_weights.original,
                    "hype": self._config.retrieval.fusion_weights.hype,
                    "bm25": self._config.retrieval.fusion_weights.bm25,
                },
            )
        return self._cached_fusion

    def _get_reranker(self) -> Any:
        """Get or create the reranker instance."""
        if "reranker" not in self._components:
            from quantumrag.core.retrieve.reranker import create_reranker

            cfg = self._config.models.reranker
            kwargs: dict[str, Any] = {}
            if cfg.model:
                kwargs["model_name" if cfg.provider in ("flashrank", "bge") else "model"] = (
                    cfg.model
                )
            self._components["reranker"] = create_reranker(cfg.provider, **kwargs)
        return self._components["reranker"]

    async def _do_retrieval(
        self,
        query: str,
        classification: QueryClassification,
        top_k: int,
        filters: dict[str, Any] | None = None,
        rerank: bool | None = None,
        pipeline_context: PipelineContext | None = None,
    ) -> Any:
        """Execute retrieval pipeline."""
        from quantumrag.core.retrieve.retriever import Retriever

        fusion = self._get_fusion_retriever()

        use_rerank = rerank if rerank is not None else self._config.retrieval.rerank
        skip_rerank = classification.complexity == QueryComplexity.SIMPLE or not use_rerank
        skip_compression = classification.complexity == QueryComplexity.SIMPLE

        reranker = self._get_reranker() if not skip_rerank else None

        retriever = Retriever(
            fusion_retriever=fusion,
            reranker=reranker,
            enable_rerank=not skip_rerank,
            enable_compression=not skip_compression,
            compression_ratio=0.7,  # Keep 70% of content (was 50%)
            fusion_candidate_multiplier=self._config.retrieval.fusion_candidate_multiplier,
            document_store=self._get_document_store(),
            enable_sibling_expansion=self._chunk_graph is None,  # Only if no graph
        )

        result = await retriever.retrieve(
            query,
            top_k=top_k,
            filters=filters,
            skip_rerank=skip_rerank,
            skip_compression=skip_compression,
            pipeline_context=pipeline_context,
        )

        # Constellation Expansion — use pre-computed graph for O(1) context assembly
        if self._chunk_graph and result.chunks:
            from quantumrag.core.retrieve.constellation import expand_with_constellation

            # Query-aware expansion: detect domains for score boosting
            query_domains: list[str] | None = None
            try:
                from quantumrag.core.ingest.indexer.fact_extractor import detect_domains

                query_domains = detect_domains(query) or None
            except Exception:
                pass

            t_const = time.perf_counter()
            result.chunks = await expand_with_constellation(
                result.chunks,
                self._chunk_graph,
                self._get_document_store(),
                top_k=top_k,
                max_expansion=top_k + 5,  # Generous expansion to catch siblings
                query_domains=query_domains,
            )
            const_ms = (time.perf_counter() - t_const) * 1000
            from quantumrag.core.models import TraceStep

            result.trace.append(
                TraceStep(
                    step="constellation_expansion",
                    result=f"{len(result.chunks)} chunks after graph expansion",
                    latency_ms=const_ms,
                    details={"query_domains": query_domains} if query_domains else {},
                )
            )

        return result

    async def _do_retrieval_retry(
        self,
        query: str,
        classification: QueryClassification,
        top_k: int,
        filters: dict[str, Any] | None = None,
        rerank: bool | None = None,
        pipeline_context: PipelineContext | None = None,
    ) -> Any:
        """Execute retrieval with BM25-dominant fusion weights and no compression.

        Used as a retry strategy when the first attempt yields insufficient evidence.
        """
        from quantumrag.core.retrieve.fusion import FusionRetriever
        from quantumrag.core.retrieve.retriever import Retriever

        # Build a BM25-dominant fusion retriever (not cached — retry-specific weights)
        retry_fusion = FusionRetriever(
            vector_store=self._get_vector_store("original"),
            hype_vector_store=self._get_vector_store("hype"),
            bm25_store=self._get_bm25_store(),
            embedding_provider=self._get_embedding_provider(),
            document_store=self._get_document_store(),
            weights={"original": 0.15, "hype": 0.15, "bm25": 0.70},
        )

        use_rerank = rerank if rerank is not None else self._config.retrieval.rerank
        skip_rerank = classification.complexity == QueryComplexity.SIMPLE or not use_rerank
        reranker = self._get_reranker() if not skip_rerank else None

        retriever = Retriever(
            fusion_retriever=retry_fusion,
            reranker=reranker,
            enable_rerank=not skip_rerank,
            enable_compression=False,  # Skip compression — pass full chunks
            fusion_candidate_multiplier=self._config.retrieval.fusion_candidate_multiplier,
            document_store=self._get_document_store(),
            enable_sibling_expansion=self._chunk_graph is None,
        )

        result = await retriever.retrieve(
            query,
            top_k=top_k,
            filters=filters,
            skip_rerank=skip_rerank,
            skip_compression=True,  # Pass full chunks to LLM
            pipeline_context=pipeline_context,
        )

        # Constellation Expansion (same as _do_retrieval, with query-aware domains)
        if self._chunk_graph and result.chunks:
            from quantumrag.core.retrieve.constellation import expand_with_constellation

            query_domains: list[str] | None = None
            try:
                from quantumrag.core.ingest.indexer.fact_extractor import detect_domains

                query_domains = detect_domains(query) or None
            except Exception:
                pass

            t_const = time.perf_counter()
            result.chunks = await expand_with_constellation(
                result.chunks,
                self._chunk_graph,
                self._get_document_store(),
                top_k=top_k,
                max_expansion=top_k + 5,
                query_domains=query_domains,
            )
            const_ms = (time.perf_counter() - t_const) * 1000
            result.trace.append(
                TraceStep(
                    step="constellation_expansion",
                    result=f"{len(result.chunks)} chunks after graph expansion",
                    latency_ms=const_ms,
                )
            )

        return result

    def status(self) -> dict[str, Any]:
        """Get engine status."""
        self._ensure_initialized()
        doc_store = self._get_document_store()
        doc_count = _run_sync(doc_store.count_documents())
        chunk_count = _run_sync(doc_store.count_chunks())

        return {
            "project_name": self._config.project_name,
            "documents": doc_count,
            "chunks": chunk_count,
            "data_dir": self._config.storage.data_dir,
            "embedding_model": self._config.models.embedding.model,
            "language": self._config.language,
        }

    def evaluate(self, **kwargs: Any) -> EvalResult:
        """Run evaluation using the Evaluator pipeline."""
        from quantumrag.core.evaluate.evaluator import Evaluator

        evaluator = Evaluator(engine=self)
        return _run_sync(evaluator.evaluate(**kwargs))


class _EngineRetrieverAdapter:
    """Adapter bridging Engine retrieval methods to the PostProcessor protocol."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    async def retrieve(
        self,
        query: Any,
        classification: Any,
        top_k: Any,
        filters: Any,
        rerank: Any,
        pipeline_ctx: Any,
    ) -> Any:
        return await self._engine._do_retrieval(
            query, classification, top_k, filters, rerank, pipeline_ctx
        )

    async def retrieve_bm25_dominant(
        self,
        query: Any,
        classification: Any,
        top_k: Any,
        filters: Any,
        rerank: Any,
        pipeline_ctx: Any,
    ) -> Any:
        return await self._engine._do_retrieval_retry(
            query, classification, top_k, filters, rerank, pipeline_ctx
        )


def _apply_doc_coherence_boost(
    chunks: list[Any],
) -> list[Any]:
    """Boost scores of chunks from documents with multiple hits.

    When several chunks from the same document appear in retrieval results,
    that document is likely more relevant. Give each chunk a small boost
    proportional to how many sibling chunks were also retrieved.
    """
    from collections import Counter

    doc_counts = Counter(sc.chunk.document_id for sc in chunks)
    if not doc_counts or max(doc_counts.values()) <= 1:
        return chunks  # No multi-hit documents, skip

    for sc in chunks:
        count = doc_counts[sc.chunk.document_id]
        if count > 1:
            # Boost: 5% per additional sibling chunk, capped at 20%
            boost = min((count - 1) * 0.05, 0.20)
            sc.score = sc.score * (1.0 + boost)

    chunks.sort(key=lambda sc: sc.score, reverse=True)
    return chunks


class IngestResult:
    """Result of an ingest operation."""

    __slots__ = ("chunks", "documents", "elapsed_seconds", "errors")

    def __init__(
        self,
        documents: int = 0,
        chunks: int = 0,
        elapsed_seconds: float = 0.0,
        errors: list[str] | None = None,
    ) -> None:
        self.documents = documents
        self.chunks = chunks
        self.elapsed_seconds = elapsed_seconds
        self.errors = errors or []
