# QuantumRAG

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange.svg)]()
[![Scenario Tests](https://img.shields.io/badge/scenario_tests-86%2F87_passed-brightgreen.svg)]()
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

[English](README.md) | [한국어](README.ko.md)

**Index-Heavy, Query-Light RAG Engine** — Put in docs, ask questions, it just works.

QuantumRAG is an open-source RAG engine that deeply understands your documents at indexing time — extracting entities, building fact indexes, generating searchable synonyms, and pre-computing chunk relationships — so that every query is fast, precise, and grounded in evidence. By combining **Triple Index Fusion** (Original Embedding + HyPE + Contextual BM25) with **4-Level Indexing** (Multi-Resolution Summaries, Structured Fact Extraction, Derived Index Enrichment, Entity-Centric Reverse Index), QuantumRAG achieves 98.9% accuracy across 87 real-world scenario tests — including multi-hop reasoning, entity-specific filtering, and cross-document verification that conventional embedding-only RAG systems cannot handle.

> **[Why QuantumRAG?](docs/en/introduction.md)** — The problems with current RAG systems, and how QuantumRAG solves them.

---

## Key Features

### Retrieval

- **Triple Index Fusion** — Original Embedding + [HyPE](https://arxiv.org/abs/2404.01765) (Hypothetical Prompt Embedding) + Contextual BM25, combined via Reciprocal Rank Fusion (RRF)
- **4-Level Indexing** — Multi-Resolution summaries, Structured Fact extraction, Derived synonym/hierarchy terms, Entity-Centric reverse index
- **Adaptive Query Routing** — Automatic classification into Simple / Medium / Complex paths with per-tier model selection
- **Entity-Centric Reverse Index** — Exact-match recall for entity IDs (`SEC-001`, `PAT-003`), attribute filters (`severity:Critical`), and range queries (`severity >= High`)

### Generation

- **Source-Grounded Generation** — Every answer cites specific chunks with inline `[1]`, `[2]` references
- **Map-Reduce RAG** — Parallel extraction + aggregation for enumeration and cross-document queries
- **Query Decomposition** — Compound questions are split into sub-queries for independent retrieval
- **Confidence Assessment** — `STRONGLY_SUPPORTED`, `PARTIALLY_SUPPORTED`, or `INSUFFICIENT_EVIDENCE` with configurable thresholds

### Infrastructure

- **Korean-First** — Native HWP/HWPX parsing, Kiwi morphological analysis, EUC-KR encoding, bilingual prompts
- **Multi-Format Parsing** — PDF, DOCX, PPTX, XLSX, HTML, Markdown, CSV, HWP/HWPX, plain text
- **Multi-Provider LLM** — OpenAI, Anthropic, Google Gemini, Ollama (local) with per-tier configuration
- **HTTP API** — FastAPI server with SSE streaming, API key auth, rate limiting
- **Built-in Evaluation** — Synthetic QA generation, Recall@K, Faithfulness, Answer Relevancy, Completeness metrics
- **Plugin System** — Extend with custom parsers, chunkers, retrievers, generators
- **Multi-Tenant** — Isolated storage per tenant with configurable limits
- **Data Connectors** — Local filesystem, Google Drive, Notion, AWS S3, Web URL

## How It Works

### Indexing Pipeline (ingest time — heavy)

```
Documents (PDF, DOCX, HWP, ...)
  ├─ Parse & Chunk (auto/semantic/fixed/structural strategies)
  ├─ Multi-Resolution Summaries (document → section → chunk)
  ├─ Structured Fact Extraction (entities, attributes, relations)
  ├─ Derived Index Enrichment (synonyms, hierarchy terms for BM25)
  ├─ Entity-Centric Reverse Index (entity → chunk_id mapping)
  └─ Triple Index Build
       ├─ Original Embedding (text-embedding-3-small)
       ├─ HyPE Embedding (hypothetical questions → embeddings)
       └─ Contextual BM25 (Kiwi morphology tokenized terms)
```

### Query Pipeline (query time — light)

```
User Query
  ├─ Query Rewrite / Decomposition
  ├─ Entity Detection (IDs, severity filters, status filters)
  ├─ Adaptive Routing (simple → nano, medium → mini, complex → full)
  ├─ Triple Index Fusion Search (RRF: 0.4 / 0.35 / 0.25)
  ├─ Entity Index Injection (exact-match chunks merged into results)
  ├─ Reranking (FlashRank / BGE / Cohere / Jina)
  ├─ Context Compression (extractive, query-aware)
  ├─ Source-Grounded Generation (with citations)
  └─ Confidence Assessment → Answer [1][2]
```

## Quick Start

### Installation

```bash
pip install quantumrag

# With all dependencies (recommended)
pip install quantumrag[all]

# Minimal + Korean support only
pip install quantumrag[korean]
```

### Python SDK

```python
from quantumrag import Engine

engine = Engine()
engine.ingest("./docs")
result = engine.query("How does the Triple Index Fusion work?")
print(result.answer)
# Sources: [1] architecture.md (§Triple Index), [2] configuration.md (§Retrieval)
```

### CLI

```bash
# Initialize a project
quantumrag init

# Ingest documents
quantumrag ingest ./docs --recursive

# Ask a question
quantumrag query "What chunking strategies are available?"

# Watch mode — auto-ingest on file changes
quantumrag ingest ./docs --watch

# Start HTTP API server
quantumrag serve --port 8000
```

### Local Models (No API Key)

```python
from quantumrag import Engine

engine = Engine(
    embedding_model="nomic-embed-text",
    generation_model="llama3.2",
)
engine.ingest("./docs")
result = engine.query("Summarize the documents")
```

## Configuration

```yaml
# quantumrag.yaml
project_name: "my-knowledge-base"
language: "ko"                          # ko, en, auto
domain: "general"                       # general, legal, medical, financial, technical

models:
  embedding:
    provider: "openai"                  # openai, gemini, ollama, local
    model: "text-embedding-3-small"
  generation:
    simple:
      provider: "openai"
      model: "gpt-5.4-nano"            # Low-cost for simple queries (~70%)
    medium:
      provider: "openai"
      model: "gpt-5.4-mini"            # Mid-tier for moderate queries (~20%)
    complex:
      provider: "anthropic"
      model: "claude-sonnet-4-20250514" # Full model for complex queries (~10%)
  reranker:
    provider: "flashrank"               # flashrank (free/CPU), bge, cohere, jina
  hype:
    provider: "openai"
    model: "gpt-5.4-nano"
    questions_per_chunk: 3

retrieval:
  top_k: 7
  fusion_weights:
    original: 0.4
    hype: 0.35
    bm25: 0.25
  rerank: true
  compression: true

storage:
  vector_db: "lancedb"
  document_store: "sqlite"
  data_dir: "./quantumrag_data"
```

Environment variables override config (prefix: `QUANTUMRAG_`):

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export QUANTUMRAG_LANGUAGE=ko
# Nested: QUANTUMRAG_MODELS__EMBEDDING__PROVIDER=gemini
```

## HTTP API

```bash
quantumrag serve --port 8000
```

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/v1/ingest` | Ingest documents from path |
| `POST` | `/v1/ingest/upload` | Upload and ingest files |
| `POST` | `/v1/ingest/text` | Ingest raw text |
| `POST` | `/v1/query` | Query (sync) |
| `POST` | `/v1/query/stream` | Query (SSE streaming) |
| `GET` | `/v1/documents` | List documents |
| `DELETE` | `/v1/documents/{id}` | Delete a document |
| `GET` | `/v1/status` | Engine status |
| `POST` | `/v1/evaluate` | Run evaluation |
| `POST` | `/v1/feedback` | Submit feedback |
| `GET` | `/health` | Health check |

Interactive docs: `http://localhost:8000/docs`

## Korean Support

QuantumRAG is built with first-class Korean language support:

| Feature | Description |
|---------|-------------|
| **HWP/HWPX Parsing** | Native parsing for Korean government/office documents |
| **Kiwi Morphology** | Accurate Korean tokenization for BM25 indexing |
| **EUC-KR Encoding** | Automatic legacy encoding detection and conversion |
| **Mixed Script** | Optimal tokenizer selection for Korean-English mixed text |
| **Bilingual Prompts** | System prompts switch between Korean/English based on query language |
| **Korean Query Patterns** | Agglutinative morphology-aware query routing and decomposition |

```bash
pip install kiwipiepy  # Required for Korean morphology
```

## Evaluation

QuantumRAG includes a built-in evaluation system with 6 metrics:

```python
engine = Engine()
result = engine.evaluate()
print(result.summary)
# retrieval_recall: 0.92
# faithfulness: 0.95
# answer_relevancy: 0.88
# completeness: 0.85
# latency: 1.2s avg
# cost: $0.003/query avg
```

### Scenario Test Suite

87 end-to-end scenario tests across 16 categories with 4 difficulty levels:

| Category | Tests | Description |
|----------|:-----:|-------------|
| Factual Confirmation | 7 | Basic fact retrieval, personnel, dates |
| Multi-Hop Reasoning | 6 | Cross-document information fusion |
| Numerical Calculations | 6 | Math, percentages, comparisons |
| Temporal Reasoning | 6 | Timeline, changelog, version tracking |
| Negation/Exclusion | 5 | "Not supported", incomplete features |
| Cross-Document Synthesis | 5 | Multi-source data integration |
| Paraphrase Robustness | 6 | Colloquial and rephrased queries |
| Multi-Turn Conversation | 5 | Coreference resolution, entity tracking |
| Edge Cases | 7 | Boundary inputs, adversarial queries |
| Precision Search | 6 | Fine-grained detail extraction |
| Implicit Inference | 5 | Information not directly stated |
| Competitive Analysis | 3 | Market positioning, competitor comparison |
| Conditional Reasoning | 5 | IF/THEN scenarios, sufficiency checks |
| Multi-Constraint Filtering | 5 | Multiple criteria intersection |
| Derived Quantitative | 5 | Calculations from multiple sources |
| Cross-Verification | 4 | Consistency checks across documents |

```bash
uv run python tests/run_scenario_tests.py
```

## Project Structure

```
quantumrag/
├── core/
│   ├── engine.py              # Single entry point
│   ├── config.py              # Configuration (Pydantic + YAML)
│   ├── models.py              # Data models (Chunk, QueryResult, ...)
│   ├── ingest/
│   │   ├── parser/            # Multi-format document parsing
│   │   ├── chunker/           # 6 chunking strategies
│   │   └── indexer/           # Triple Index + 4-Level Indexing
│   │       ├── triple_index_builder.py
│   │       ├── multi_resolution.py
│   │       ├── fact_extractor.py
│   │       ├── derived_index.py
│   │       └── entity_index.py
│   ├── retrieve/
│   │   ├── fusion.py          # RRF triple index fusion
│   │   ├── reranker.py        # Multi-provider reranking
│   │   ├── compressor.py      # Context compression
│   │   ├── entity_detector.py # Entity query detection
│   │   └── constellation.py   # Chunk relationship graph
│   ├── generate/
│   │   ├── generator.py       # Source-grounded generation
│   │   ├── router.py          # Query complexity routing
│   │   ├── rewriter.py        # Query rewriting
│   │   ├── map_reduce.py      # Map-Reduce for aggregation
│   │   └── decomposer.py      # Query decomposition
│   ├── storage/               # SQLite + LanceDB + Tantivy
│   ├── llm/                   # Provider abstraction layer
│   │   └── providers/         # OpenAI, Anthropic, Gemini, Ollama
│   ├── evaluate/              # Evaluation metrics & synthetic QA
│   ├── cache/                 # Semantic cache
│   ├── security/              # Input sanitization, API auth
│   ├── observability/         # Structured logging, tracing
│   └── multitenancy/          # Tenant isolation
├── api/                       # FastAPI HTTP server
├── cli/                       # Typer CLI
├── connectors/                # File, GDrive, Notion, S3, URL
├── korean/                    # Kiwi morphology, encoding
└── plugins/                   # Plugin registry & hooks
```

## Comparison

| Feature | QuantumRAG | LangChain | LlamaIndex | OpenAI file_search |
|---------|:----------:|:---------:|:----------:|:------------------:|
| Triple Index (Embedding + HyPE + BM25) | Yes | No | No | No |
| 4-Level Indexing | Yes | No | No | No |
| Entity-Centric Reverse Index | Yes | No | No | No |
| Index-Heavy Architecture | Yes | No | Partial | No |
| Korean Language (HWP, Kiwi) | Native | Plugin | Plugin | No |
| Adaptive Query Routing | Yes | Manual | No | No |
| Map-Reduce RAG | Yes | Yes | Yes | No |
| Offline / Local LLM | Yes (Ollama) | Yes | Yes | No |
| Built-in Evaluation | Yes | Via LangSmith | Yes | No |
| Zero GPU Required | Yes | Depends | Depends | N/A |

## Development

```bash
git clone https://github.com/quantumaikr/quantumrag.git
cd quantumrag
pip install -e ".[dev,all]"

# Run unit tests
pytest tests/ -q

# Run scenario tests
uv run python tests/run_scenario_tests.py

# Lint
ruff check quantumrag/ tests/
```

## System Requirements

- **Python**: 3.10, 3.11, 3.12
- **RAM**: 2GB minimum, 4GB+ recommended
- **GPU**: Not required (CPU-only by default)
- **Storage**: SQLite + LanceDB + Tantivy (all local, no external services)
- **OS**: Linux, macOS, Windows (WSL2)

## License

Apache License 2.0. See [LICENSE](LICENSE).
