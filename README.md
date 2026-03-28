# QuantumRAG

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange.svg)]()
[![Scenario Tests](https://img.shields.io/badge/scenario_tests-98%2F107_passed-brightgreen.svg)]()
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

> **The result:** 91.6% accuracy across [107 real-world scenario tests](docs/reports/scenario-test-report.md) — including multi-hop reasoning, cross-document verification, numerical calculation, and entity-specific filtering that conventional RAG cannot handle.

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
  ├─ Query Rewrite / Decomposition
  ├─ Entity Detection & Attribute Filtering
  ├─ Adaptive Routing (simple → nano, medium → mini, complex → full)
  ├─ Triple Index Fusion Search (RRF: 0.4 / 0.35 / 0.25)
  ├─ Reranking (FlashRank / BGE / Cohere / Jina)
  ├─ Context Compression
  └─ Source-Grounded Generation → Answer [1][2] + Confidence
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

Built-in evaluation with 6 metrics and 87 scenario tests across 16 categories:

```python
engine = Engine()
result = engine.evaluate()
print(result.summary)
# retrieval_recall: 0.92, faithfulness: 0.95
# answer_relevancy: 0.88, completeness: 0.85
# latency: 1.2s avg, cost: $0.003/query avg
```

| Category | Tests | Category | Tests |
|----------|:-----:|----------|:-----:|
| Factual Confirmation | 7 | Precision Search | 6 |
| Multi-Hop Reasoning | 6 | Implicit Inference | 5 |
| Numerical Calculations | 6 | Competitive Analysis | 3 |
| Temporal Reasoning | 6 | Conditional Reasoning | 5 |
| Negation/Exclusion | 5 | Multi-Constraint Filtering | 5 |
| Cross-Document Synthesis | 5 | Derived Quantitative | 5 |
| Paraphrase Robustness | 6 | Cross-Verification | 4 |
| Multi-Turn Conversation | 5 | Edge Cases | 7 |

```bash
uv run python tests/run_scenario_tests.py
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
│   ├── engine.py              # Single entry point
│   ├── config.py              # Configuration (Pydantic + YAML)
│   ├── models.py              # Data models (Chunk, QueryResult, ...)
│   ├── ingest/
│   │   ├── parser/            # Multi-format document parsing
│   │   ├── chunker/           # Chunking strategies (auto/semantic/fixed/structural)
│   │   └── indexer/           # Triple Index + 4-Level Indexing
│   ├── retrieve/
│   │   ├── fusion.py          # RRF triple index fusion
│   │   ├── reranker.py        # Multi-provider reranking
│   │   └── entity_detector.py # Entity query detection
│   ├── generate/
│   │   ├── generator.py       # Source-grounded generation
│   │   ├── router.py          # Query complexity routing
│   │   └── decomposer.py      # Query decomposition
│   ├── storage/               # SQLite + LanceDB + Tantivy
│   ├── llm/                   # Provider abstraction (OpenAI, Anthropic, Gemini, Ollama)
│   ├── evaluate/              # Evaluation metrics & synthetic QA
│   └── pipeline/              # Profiling, signals, orchestration
├── api/                       # FastAPI HTTP server + web playground
├── cli/                       # Typer CLI
├── connectors/                # File, GDrive, Notion, S3, URL
├── korean/                    # Kiwi morphology, encoding
└── plugins/                   # Plugin registry & hooks
```

## Development

```bash
git clone https://github.com/quantumaikr/quantumrag.git
cd quantumrag
pip install -e ".[dev,all]"

# Run tests
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
