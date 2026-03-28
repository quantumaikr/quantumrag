# QuantumRAG

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
[![Version](https://img.shields.io/pypi/v/quantumrag.svg)](https://pypi.org/project/quantumrag/)
[![Scenario Tests](https://img.shields.io/badge/scenario_tests-176_cases-brightgreen.svg)]()
[![QA Datasets](https://img.shields.io/badge/QA_datasets-105_questions-blue.svg)]()
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

[English](README.md) | [한국어](README.ko.md)

**Open-source RAG engine that deeply indexes your documents so every answer is accurate, cited, and fast.**

```python
from quantumrag import Engine

engine = Engine()                # Zero config — auto-detects your API key
engine.ingest("./docs")          # PDF, DOCX, HWP, XLSX, PPTX, MD, CSV, TXT
result = engine.query("What are the key security findings?")
print(result.answer)
# The audit identified 3 critical findings: ... [1][2]
# Confidence: STRONGLY_SUPPORTED
```

Put documents in. Ask questions. Get cited answers. **No configuration needed.**

---

## Why QuantumRAG

Most RAG systems embed documents into vectors and hope the right chunks come back. When questions are phrased differently, when answers span multiple documents, or when you need exact entity matches — they fail silently.

QuantumRAG takes a different approach: **understand documents deeply at indexing time, so queries are fast and accurate by default.**

Every document is understood through multiple lenses — semantic meaning, hypothetical questions it could answer, keywords and synonyms, structured facts, entity relationships — and these perspectives are fused at query time to find the right answer regardless of how you phrase the question.

> **The result:** 176 scenario tests + 105 QA questions across 4 datasets — covering multi-hop reasoning, cross-document verification, numerical calculation, hallucination prevention, and entity-specific filtering that conventional RAG cannot handle.

## Three Ways to Use It

| | What you do | What happens |
|---|-------------|-------------|
| **Just use it** | `engine.ingest("./docs")` → `engine.query("...")` | Parser, chunker, index, routing — all auto-selected |
| **Tune it** | Adjust fusion weights, pick models, set domain | Better results for your specific use case |
| **Own it** | Custom parsers, chunkers, retrievers, generators | Every layer is replaceable via plugins |

Zero configuration to first answer. Full control when you need it.

## Quick Start

### Installation

```bash
pip install quantumrag

# With all dependencies (recommended)
pip install quantumrag[all]

# Minimal + Korean support only
pip install quantumrag[korean]
```

### CLI

```bash
# Initialize a project
quantumrag init

# Ingest documents
quantumrag ingest ./docs --recursive

# Ask a question
quantumrag query "What chunking strategies are available?"

# Interactive multi-turn chat
quantumrag chat

# Start HTTP API server with web playground
quantumrag serve --port 8000
```

### Zero Configuration

`Engine()` auto-detects your environment and picks the best available provider:

| Detected Key | Provider | Embedding | Generation |
|-------------|----------|-----------|------------|
| `OPENAI_API_KEY` | OpenAI | text-embedding-3-small | gpt-4.1-nano / gpt-4.1-mini |
| `GOOGLE_API_KEY` | Gemini | text-embedding-004 | gemini-2.5-flash-lite / flash |
| `ANTHROPIC_API_KEY` | Anthropic | local (bge-m3) | claude-haiku / claude-sonnet |
| *(none)* | Ollama | local (bge-m3) | llama3.2:3b |

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

## Korean Support

QuantumRAG treats Korean as a first language, not a translation.

| Feature | Description |
|---------|-------------|
| **HWP/HWPX Parsing** | Native parsing for Korean government/office documents |
| **Kiwi Morphology** | Accurate Korean tokenization for BM25 indexing |
| **EUC-KR Encoding** | Automatic legacy encoding detection and conversion |
| **Mixed Script** | Optimal tokenizer selection for Korean-English mixed text |
| **Bilingual Prompts** | System prompts switch based on query language |
| **Korean Query Patterns** | Agglutinative morphology-aware query routing |

```bash
pip install kiwipiepy  # Required for Korean morphology
```

## How It Works

### Index-Heavy, Query-Light

The core design: expensive computation happens once at ingestion, enabling cheap and precise queries.

**Indexing Pipeline (ingest time — heavy)**

```
Documents (PDF, DOCX, HWP, PPTX, XLSX, HTML, MD, CSV, TXT)
  ├─ Auto-select parser & chunking strategy
  ├─ Multi-Resolution Summaries (document → section → chunk)
  ├─ Structured Fact Extraction (entities, attributes, relations)
  ├─ Derived Index Enrichment (synonyms, hierarchy terms)
  ├─ Entity-Centric Reverse Index (entity → chunk_id mapping)
  └─ Triple Index Build
       ├─ Original Embedding (semantic meaning)
       ├─ HyPE Embedding (hypothetical questions → embeddings)
       └─ Contextual BM25 (morphology-aware keyword index)
```

**Query Pipeline (query time — light)**

```
User Query
  ├─ Query Rewrite / Expansion
  ├─ Entity Detection & Attribute Filtering
  ├─ Adaptive Routing (simple → nano, medium → mini, complex → full)
  ├─ Triple Index Fusion Search (RRF: 0.4 / 0.35 / 0.25)
  ├─ Reranking (FlashRank / BGE / Cohere / Jina)
  ├─ Context Compression
  ├─ Source-Grounded Generation → Answer [1][2] + Confidence
  └─ Post-Correction (Retrieval Retry → Self-Correct → Fact Verify → Completeness)
```

### Triple Index Fusion

Three retrieval methods combined via Reciprocal Rank Fusion — each catches what the others miss:

| Index | What it finds | Why it matters |
|-------|--------------|----------------|
| **Original Embedding** | Semantically similar content | Handles paraphrasing and conceptual queries |
| **HyPE Embedding** | Content that answers similar questions | Bridges the question↔document gap |
| **Contextual BM25** | Exact keyword and entity matches | Precise when you know what you're looking for |

### 4-Level Indexing

All rule-based, zero LLM cost at ingest time:

1. **Multi-Resolution Summaries** — Document, section, and chunk-level for breadth
2. **Structured Fact Extraction** — Domain-aware patterns (IDs, severity, versions, contracts)
3. **Derived Index Enrichment** — Synonyms and hierarchy terms boost BM25 recall
4. **Entity-Centric Reverse Index** — Complete recall for entity queries and attribute filters

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

Web playground: `http://localhost:8000/playground`
Interactive API docs: `http://localhost:8000/docs`

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
```

## Evaluation

### Built-in Evaluation

6 metrics, 176 scenario tests, and 4 QA datasets (105 questions):

```python
engine = Engine()
result = engine.evaluate()
print(result.summary)
# retrieval_recall: 0.92, faithfulness: 0.95
# answer_relevancy: 0.88, completeness: 0.85
```

### QA Datasets

Real-world web content used for systematic RAG validation:

| Dataset | Focus | Questions | Pass Rate |
|---------|-------|:---------:|:---------:|
| ds-001 | Multilingual + numerical precision | 20 | 85-100% |
| ds-002 | Type system + cross-topic confusion | 25 | 88% |
| ds-003 | Dense technical + cross-document | 30 | 83-87% |
| ds-004 | Table extraction + contradiction detection | 30 | 77-90% |
| **Combined** | **All sources merged (retrieval stress test)** | **105** | **29%** |

The Combined QA test reveals that retrieval precision is the key bottleneck at scale: 68 of 75 failures are retrieval-caused. This is the primary area for improvement.

```bash
# Individual dataset
.venv/bin/python datasets/run_qa.py ds-001

# Combined (retrieval precision test)
.venv/bin/python datasets/run_qa_combined.py

# Scenario tests
make scenario-test
```

## Comparison

LangChain and LlamaIndex give you building blocks. OpenAI gives you a black box. QuantumRAG gives you an **engine** — opinionated defaults that work, with every layer customizable.

| Feature | QuantumRAG | LangChain | LlamaIndex | OpenAI file_search |
|---------|:----------:|:---------:|:----------:|:------------------:|
| Triple Index (Embedding + HyPE + BM25) | Yes | No | No | No |
| 4-Level Indexing | Yes | No | No | No |
| Entity-Centric Reverse Index | Yes | No | No | No |
| Korean Language (HWP, Kiwi) | Native | Plugin | Plugin | No |
| Adaptive Query Routing | Yes | Manual | No | No |
| Offline / Local LLM | Yes (Ollama) | Yes | Yes | No |
| Built-in Evaluation | Yes | Via LangSmith | Yes | No |
| Zero GPU Required | Yes | Depends | Depends | N/A |
| Zero Config to First Answer | Yes | No | No | Partial |

## Project Structure

```
quantumrag/
├── core/
│   ├── engine.py              # Single entry point for all operations
│   ├── config.py              # Configuration (Pydantic + YAML + env vars)
│   ├── models.py              # Data models (Chunk, Source, QueryResult, ...)
│   ├── ingest/
│   │   ├── parser/            # PDF, DOCX, PPTX, XLSX, HWP, HTML, MD, CSV, TXT
│   │   ├── chunker/           # Strategies: auto, semantic, fixed, structural
│   │   ├── indexer/           # Triple Index + 4-Level Indexing + fact extraction
│   │   └── denoiser.py        # Input quality filtering
│   ├── retrieve/
│   │   ├── fusion.py          # RRF triple index fusion search
│   │   ├── reranker.py        # FlashRank, BGE, Cohere, Jina
│   │   ├── query_classifier.py # Adaptive complexity routing
│   │   ├── entity_detector.py # Entity query detection + attribute filtering
│   │   └── fact_index.py      # Structured fact lookup
│   ├── generate/
│   │   ├── generator.py       # Source-grounded generation with citations
│   │   ├── router.py          # Simple/Medium/Complex query routing
│   │   ├── fact_verifier.py   # Hallucination detection (zero LLM cost)
│   │   ├── completeness.py    # Multi-part answer verification
│   │   ├── map_reduce.py      # Aggregation query processing
│   │   └── query_expander.py  # Colloquial → formal query expansion
│   ├── pipeline/
│   │   ├── postprocess.py     # Correction chain (retry → verify → complete)
│   │   └── context.py         # Pipeline context and document profiling
│   ├── storage/               # SQLite, LanceDB, Tantivy, Chroma, FAISS
│   ├── llm/                   # OpenAI, Anthropic, Gemini, Ollama
│   ├── autotune/              # Parameter optimization framework
│   ├── cache/                 # Semantic cache with TTL
│   └── evaluate/              # Metrics, synthetic QA generation
├── api/                       # FastAPI HTTP server + web playground
├── cli/                       # Typer CLI (init, ingest, query, serve, status)
├── connectors/                # File, S3, URL, Google Drive, Notion
├── korean/                    # Kiwi morphology, EUC-KR encoding
├── plugins/                   # Plugin registry & hook system
datasets/                      # QA datasets (4 datasets, 105 questions)
├── run_qa.py                  # Individual dataset runner
├── run_qa_combined.py         # Combined retrieval stress test
└── STATUS.md                  # Auto-generated dashboard
tests/
├── unit/                      # 782 unit tests
├── scenarios/                 # 176 scenario test cases (v1-v4)
├── security/                  # SSRF, path traversal, injection tests
└── scale/                     # Scale testing framework
```

## Development

```bash
git clone https://github.com/quantumaikr/quantumrag.git
cd quantumrag
uv sync --dev

# Tiered testing
make quick           # Lint only (0.1s)
make smoke           # Lint + core tests (2s)
make check           # Lint + all unit tests (7s)
make scenario-test   # Scenario tests (requires API keys)

# Target-specific tests
make test-gen        # Generation tests
make test-ret        # Retrieval tests
make test-ingest     # Ingest tests
make test-api        # API/CLI tests

# Utilities
make fix             # Auto-fix lint issues
make help            # All available commands
```

## System Requirements

- **Python**: 3.10, 3.11, 3.12
- **RAM**: 2GB minimum, 4GB+ recommended
- **GPU**: Not required (CPU-only by default)
- **Storage**: SQLite + LanceDB + Tantivy (all local, no external services)
- **OS**: Linux, macOS, Windows (WSL2)

## Documentation

Full documentation in [English](docs/en/index.md) and [Korean](docs/ko/index.md):

- [Getting Started](docs/en/getting-started.md) / [시작하기](docs/ko/getting-started.md)
- [Architecture](docs/en/architecture.md) / [아키텍처](docs/ko/architecture.md)
- [Configuration](docs/en/configuration.md) / [설정 가이드](docs/ko/configuration.md)
- [API Reference](docs/en/api-reference.md) / [API 레퍼런스](docs/ko/api-reference.md)
- [Evaluation](docs/en/evaluation.md) / [평가 시스템](docs/ko/evaluation.md)
- [Troubleshooting](docs/en/troubleshooting.md) / [트러블슈팅](docs/ko/troubleshooting.md)

## License

Apache License 2.0. See [LICENSE](LICENSE).
