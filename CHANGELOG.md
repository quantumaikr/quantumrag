# Changelog

All notable changes to QuantumRAG will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-03-25

### Added

**Core Engine**
- Engine class as single entry point for all RAG functionality
- Sync and async interfaces for all operations
- Adaptive complexity routing (Simple/Medium/Complex query paths)
- Configurable via YAML, environment variables, and code arguments

**Triple Index Architecture**
- Original Embedding index (cosine similarity via LanceDB)
- HyPE (Hypothetical Prompt Embeddings) index for question-to-question matching
- Contextual BM25 index (tantivy-py) with Korean morphology support
- Reciprocal Rank Fusion (RRF) with configurable weights

**Document Ingestion**
- Multi-format parsing: PDF, DOCX, PPTX, XLSX, HTML, Markdown, CSV, HWP/HWPX, plain text
- Three chunking strategies: fixed-size, semantic, structural (auto-detection)
- Contextual prefix generation for enhanced BM25 indexing
- Quality scoring (0.0-1.0) for parsed documents
- Incremental indexing (hash-based change detection)

**Retrieval Pipeline**
- Triple Index fusion search with RRF scoring
- FlashRank reranking (CPU, free)
- Extractive context compression
- Metadata-based filtering
- Full processing trace for debugging

**Generation**
- Source-grounded generation with inline citations [1], [2]
- Korean/English bilingual prompt system
- Confidence assessment (strongly_supported, partially_supported, insufficient_evidence)
- "I don't know" responses when evidence is insufficient
- Streaming support (SSE)

**LLM Providers**
- OpenAI (GPT-4.1 family, embeddings)
- Anthropic (Claude family)
- Ollama (local models, no API key needed)
- Automatic retry with exponential backoff
- Cost tracking and usage monitoring

**Korean Language Support**
- HWP/HWPX document parsing
- Kiwi morphology analyzer integration
- EUC-KR/CP949 encoding detection and conversion
- Korean-aware query routing (substring matching for agglutinative morphology)

**HTTP API (FastAPI)**
- POST /v1/ingest, /v1/query, /v1/query/stream
- GET /v1/documents, /v1/status
- DELETE /v1/documents/:id
- POST /v1/evaluate, /v1/feedback
- API key authentication
- Rate limiting
- CORS configuration

**Evaluation System**
- Synthetic QA pair generation (template-based, zero cost)
- Retrieval Recall@K metric
- Faithfulness metric (sentence-level)
- Answer Relevancy metric
- Latency percentiles (P50, P95, P99)
- Weakness analysis with improvement suggestions

**CLI (Typer)**
- `quantumrag init` - Initialize project
- `quantumrag ingest <path>` - Ingest documents
- `quantumrag query "<question>"` - Query with citations
- `quantumrag status` - Show index status
- `quantumrag serve` - Start HTTP API server
- Rich progress bars and formatted output

**Advanced Features**
- Plugin system with hook-based extensibility
- Semantic cache with TTL and similarity matching
- Batch query processing with concurrency control
- Query tracing and cost tracking (observability)

**Connectors**
- Local file system
- URL/web page
- AWS S3

## [0.2.0] - 2026-03-29

### Added
- Post-generation correction pipeline (retrieval retry → self-correct → fact verify → completeness)
- Fact verifier: rule-based hallucination detection via fact cross-checking (zero LLM cost)
- Completeness checker: multi-part answer verification with targeted re-retrieval
- Query classifier for adaptive routing
- Autotune framework for parameter optimization
- Chunk coherence scoring and input denoising
- Chroma and FAISS vector store backends
- Map-Reduce RAG for aggregation queries
- QA dataset framework with 4 datasets (105 questions), auto-graduation
- Combined QA runner for retrieval precision testing at scale
- Scenario test suite (v1-v4, 176 test cases)
- Scale test framework
- Makefile with tiered test strategy (quick/smoke/check/scenario)
- GitHub Actions CI: mypy type checking, security tests, coverage threshold

### Removed
- Multi-tenant support (isolated storage) — removed, not needed for current use cases
- Query decomposition module (decomposer.py) — replaced by query expander
- Speculative RAG (speculative.py) — replaced by post-generation correction pipeline
- Evidence extractor — functionality merged into fact extractor
