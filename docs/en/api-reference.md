# API Reference

> HTTP API and Python SDK reference.

---

## Python SDK

### Engine

The `Engine` class is the single entry point for all QuantumRAG functionality.

```python
from quantumrag import Engine
```

#### Constructor

```python
Engine(
    config: str | Path | QuantumRAGConfig | None = None,
    *,
    document_store: Any | None = None,    # Inject custom store
    vector_store: Any | None = None,      # Inject custom store
    bm25_store: Any | None = None,        # Inject custom store
    embedding_model: str | None = None,   # Quick override
    generation_model: str | None = None,  # Quick override
    data_dir: str | None = None,          # Quick override
)
```

#### Methods

**`ingest(path, *, chunking_strategy=None, metadata=None, recursive=True, enable_hype=True) → IngestResult`**

Ingest documents from a file or directory.

```python
result = engine.ingest("./docs", recursive=True)
print(result.documents)       # Number of documents processed
print(result.chunks)          # Number of chunks created
print(result.elapsed_seconds) # Time taken
print(result.errors)          # List of error messages
```

Parameters:
- `path` — File or directory path
- `chunking_strategy` — Override: `"auto"`, `"structural"`, `"semantic"`, `"fixed"`
- `metadata` — Custom metadata dict attached to all documents
- `recursive` — Recurse into subdirectories (default: `True`)
- `enable_hype` — Generate HyPE embeddings (default: `True`)

**`query(query, *, filters=None, top_k=None, rerank=None, conversation_history=None) → QueryResult`**

Query the indexed documents.

```python
result = engine.query("How does adaptive query routing work?")
print(result.answer)      # Answer with inline citations
print(result.confidence)  # Confidence enum
print(result.sources)     # List[Source] with excerpts
print(result.trace)       # List[TraceStep] pipeline trace
print(result.metadata)    # tokens_used, cost, latency_ms, etc.
```

Parameters:
- `query` — Natural language question
- `filters` — Metadata filters (dict)
- `top_k` — Override retrieval count
- `rerank` — Override reranking (bool)
- `conversation_history` — List of `ConversationTurn` for multi-turn

**`query_stream(query, *, filters=None, top_k=None) → AsyncIterator[str]`**

Stream answer tokens.

```python
async for token in engine.query_stream("What reranking providers are supported?"):
    print(token, end="", flush=True)
```

**`evaluate(**kwargs) → EvalResult`**

Run the evaluation pipeline.

```python
result = engine.evaluate()
print(result.summary)
for metric in result.metrics:
    print(f"{metric.name}: {metric.score:.2f}")
for suggestion in result.suggestions:
    print(f"- {suggestion}")
```

**`status() → dict`**

Get engine status.

```python
status = engine.status()
# {'documents': 15, 'chunks': 234, 'config': {...}, 'data_dir': '...'}
```

### Data Models

**QueryResult**

```python
@dataclass
class QueryResult:
    answer: str                    # Generated answer with citations
    sources: list[Source]          # Source references
    confidence: Confidence         # STRONGLY_SUPPORTED | PARTIALLY_SUPPORTED | INSUFFICIENT_EVIDENCE
    trace: list[TraceStep]         # Pipeline execution trace
    metadata: dict[str, Any]       # tokens_used, cost, latency_ms, path, etc.
```

**Source**

```python
@dataclass
class Source:
    chunk_id: str
    document_title: str
    page: int | None
    section: str | None
    excerpt: str                   # Relevant text excerpt
    relevance_score: float
```

**Confidence**

```python
class Confidence(Enum):
    STRONGLY_SUPPORTED = "STRONGLY_SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
```

**TraceStep**

```python
@dataclass
class TraceStep:
    step: str            # "rewrite", "classify", "retrieve", "generate", etc.
    result: str          # Summary of step output
    latency_ms: float
    details: dict        # Step-specific details
```

**IngestResult**

```python
@dataclass
class IngestResult:
    documents: int
    chunks: int
    elapsed_seconds: float
    errors: list[str]
```

---

## HTTP API

Start the server:

```bash
quantumrag serve --host 0.0.0.0 --port 8000
```

Interactive docs at `http://localhost:8000/docs` (Swagger UI).

### Authentication

If `QUANTUMRAG_API_KEY` is set, all `/v1/*` endpoints require the header:

```
Authorization: Bearer <api-key>
```

### Endpoints

#### `GET /health`

Health check (no auth required).

```json
{
  "status": "ok",
  "version": "0.1.0",
  "uptime_seconds": 123.4
}
```

#### `POST /v1/ingest`

Ingest documents from a filesystem path.

**Request:**

```json
{
  "path": "./docs",
  "chunking_strategy": "auto",
  "metadata": {"project": "alpha"},
  "recursive": true,
  "enable_hype": true
}
```

**Response:**

```json
{
  "documents": 15,
  "chunks": 234,
  "elapsed_seconds": 45.2,
  "errors": []
}
```

#### `POST /v1/ingest/upload`

Upload and ingest files (multipart form data).

```bash
curl -X POST http://localhost:8000/v1/ingest/upload \
  -H "Authorization: Bearer $API_KEY" \
  -F "files=@report.pdf" \
  -F "files=@data.xlsx"
```

#### `POST /v1/ingest/text`

Ingest raw text directly.

**Request:**

```json
{
  "text": "QuantumRAG supports four chunking strategies: auto, structural, semantic, and fixed...",
  "title": "Chunking Guide",
  "metadata": {"type": "documentation"}
}
```

#### `POST /v1/query`

Synchronous query.

**Request:**

```json
{
  "query": "What reranking providers are supported?",
  "filters": null,
  "top_k": 7,
  "rerank": true,
  "conversation_history": []
}
```

**Response:**

```json
{
  "answer": "QuantumRAG supports FlashRank (default, CPU-based) and Cohere reranking providers [1].",
  "sources": [
    {
      "chunk_id": "abc123",
      "document_title": "Configuration Guide",
      "page": null,
      "section": "Reranking",
      "excerpt": "FlashRank provides CPU-based reranking at no cost...",
      "relevance_score": 0.92
    }
  ],
  "confidence": "STRONGLY_SUPPORTED",
  "trace": [...],
  "metadata": {
    "tokens_used": 1250,
    "estimated_cost": 0.003,
    "latency_ms": 1450,
    "path": "MEDIUM"
  }
}
```

#### `POST /v1/query/stream`

SSE streaming query.

**Request:**

```json
{
  "query": "Summarize the key findings",
  "top_k": 7
}
```

**Response:** Server-Sent Events stream:

```
data: The
data: key
data: findings
data: include
data: ...
data: [DONE]
```

#### `GET /v1/documents`

List indexed documents.

**Query Parameters:**
- `limit` (default: 50)
- `offset` (default: 0)

**Response:**

```json
{
  "documents": [
    {
      "id": "doc-uuid",
      "title": "Q3 Report",
      "source_type": "FILE",
      "chunks": 15,
      "created_at": "2025-01-15T10:30:00Z"
    }
  ],
  "total": 15
}
```

#### `DELETE /v1/documents/{document_id}`

Delete a document and its chunks.

#### `GET /v1/status`

Engine status.

```json
{
  "documents": 15,
  "chunks": 234,
  "config": {
    "language": "ko",
    "domain": "general"
  }
}
```

#### `POST /v1/evaluate`

Run evaluation metrics.

**Request:**

```json
{
  "benchmark_file": null,
  "sample_count": 20
}
```

**Response:**

```json
{
  "metrics": [
    {"name": "retrieval_recall", "score": 0.92},
    {"name": "faithfulness", "score": 0.95},
    {"name": "answer_relevancy", "score": 0.88}
  ],
  "summary": "Overall quality: Good",
  "suggestions": ["Consider increasing top_k for complex queries"]
}
```

#### `POST /v1/feedback`

Submit user feedback on a query result.

**Request:**

```json
{
  "query": "What reranking providers are supported?",
  "answer": "QuantumRAG supports FlashRank and Cohere reranking [1].",
  "rating": 5,
  "comment": "Accurate and well-cited"
}
```

---

## CLI Reference

```bash
quantumrag [OPTIONS] COMMAND [ARGS]
```

### Global Options

| Option | Description |
|--------|-------------|
| `--verbose`, `-v` | Enable debug logging |
| `--json-log` | Output logs in JSON format |
| `--version` | Show version and exit |

### Commands

**`init`** — Create default config

```bash
quantumrag init [--config quantumrag.yaml]
```

**`ingest`** — Ingest documents

```bash
quantumrag ingest <PATH> [OPTIONS]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--config`, `-c` | Config file path | `quantumrag.yaml` |
| `--strategy`, `-s` | Chunking strategy | `auto` |
| `--metadata`, `-m` | Key=value pairs | (none) |
| `--watch`, `-w` | Watch for file changes | `false` |
| `--recursive` / `--no-recursive` | Recurse into directories | `true` |

**`query`** — Ask a question

```bash
quantumrag query "What reranking providers are supported?" [OPTIONS]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--config`, `-c` | Config file path | `quantumrag.yaml` |
| `--top-k` | Number of chunks to retrieve | from config |

**`serve`** — Start HTTP API server

```bash
quantumrag serve [OPTIONS]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--config`, `-c` | Config file path | `quantumrag.yaml` |
| `--host` | Bind address | `127.0.0.1` |
| `--port` | Bind port | `8000` |

**`status`** — Show engine status

```bash
quantumrag status [--config quantumrag.yaml]
```

**`evaluate`** — Run evaluation

```bash
quantumrag evaluate [--benchmark benchmark.json]
```
