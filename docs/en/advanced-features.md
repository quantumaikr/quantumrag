# Advanced Features

> Multi-tenancy, semantic caching, observability, security, and batch processing.

---

## Multi-Tenancy

Isolated per-tenant storage with custom configurations and quotas.

### Setup

```python
from quantumrag.core.multitenancy.tenant import TenantManager

manager = TenantManager(base_dir="/data/quantumrag")

# Create tenants
manager.create_tenant(
    "acme-corp",
    display_name="Acme Corporation",
    max_documents=10000,
    max_queries_per_day=50000,
)

manager.create_tenant(
    "beta-inc",
    display_name="Beta Inc",
    embedding_model="text-embedding-3-large",
    max_documents=5000,
)
```

### Usage

```python
# Get tenant-specific engine
engine = manager.get_engine("acme-corp")
engine.ingest("./acme_docs")
result = engine.query("What is Acme's policy?")
```

### Tenant Isolation

Each tenant gets:
- **Isolated data directory**: `/base/tenants/{tenant_id}/data`
- **Separate databases**: SQLite, LanceDB, Tantivy per tenant
- **Custom models**: Per-tenant embedding/generation models
- **Quota enforcement**: Document count, daily query limits
- **Config persistence**: `tenant.json` per tenant directory

### Tenant Configuration

```python
@dataclass
class TenantConfig:
    tenant_id: str                     # [a-zA-Z0-9][a-zA-Z0-9_-]{0,62}
    display_name: str
    data_dir: str
    embedding_model: str | None        # Override default
    generation_model: str | None       # Override default
    max_documents: int | None          # Quota
    max_queries_per_day: int | None    # Quota
    allowed_file_types: list[str]      # Restrict formats
    metadata: dict[str, Any]           # Custom fields
```

---

## Semantic Cache

Avoid redundant LLM calls by caching query results with semantic similarity matching.

### Configuration

```yaml
cost:
  semantic_cache: true
```

### How It Works

```
Query → Hash Match → Return cached result (fast path)
         │
         ▼ (no exact match)
Query → Embed → Cosine Similarity → Return cached result if > 0.95
         │
         ▼ (no semantic match)
Full Pipeline → Cache result → Return answer
```

### Cache Properties

| Property | Default |
|----------|---------|
| TTL | 3600 seconds (1 hour) |
| Max entries | 1000 |
| Similarity threshold | 0.95 |
| Storage | SQLite persistent |
| Eviction | LRU (Least Recently Used) |

### Cache API

```python
from quantumrag.core.cache.semantic import SemanticCache

cache = SemanticCache(
    ttl_seconds=3600,
    max_entries=1000,
    similarity_threshold=0.95,
    storage_path="cache.db",
)

# Exact match
cached = cache.get(query)

# Semantic match
cached = cache.get_semantic(query, query_embedding)

# Store result
cache.put(query, answer, sources, confidence, metadata)

# Statistics
stats = cache.stats()  # hits, misses, hit_rate
```

---

## Observability

### Structured Logging

QuantumRAG uses `structlog` for structured, machine-readable logs:

```python
from quantumrag.core.logging import get_logger, setup_logging

setup_logging(level="DEBUG", json_output=True)
logger = get_logger("my_module")
logger.info("query_complete", latency_ms=1450, confidence="STRONGLY_SUPPORTED")
```

Output (JSON mode):

```json
{"event": "query_complete", "latency_ms": 1450, "confidence": "STRONGLY_SUPPORTED", "timestamp": "2025-01-15T10:30:00Z"}
```

### Query Tracing

Every query produces a trace of pipeline steps:

```python
result = engine.query("What is the revenue?")
for step in result.trace:
    print(f"{step.step}: {step.latency_ms:.0f}ms - {step.result}")
```

Example trace:

```
rewrite: 0ms - No rewrite needed
classify: 150ms - MEDIUM (type: factual)
retrieve: 450ms - 7 chunks retrieved
rerank: 200ms - Top chunk score: 0.92
compress: 50ms - Compressed 7 chunks
generate: 800ms - Answer with 2 citations
```

### Trace Storage

Traces are stored in SQLite for analysis:

```python
from quantumrag.core.observability.tracer import TraceStore

tracer = TraceStore(db_path="traces.db")

# Query traces
traces = tracer.list_traces(limit=50, since=timestamp)

# Aggregate stats
stats = tracer.get_stats(since=timestamp)
# {'total_queries': 1000, 'avg_latency_ms': 1200, 'avg_cost': 0.003}
```

---

## Security

### API Authentication

```bash
export QUANTUMRAG_API_KEY=your-secret-key
quantumrag serve --port 8000
```

All `/v1/*` endpoints require:

```
Authorization: Bearer your-secret-key
```

### Path Traversal Protection

The API server validates all file paths to prevent directory traversal attacks:

1. URL decoding before validation
2. `Path.resolve()` for absolute path normalization
3. `relative_to()` for containment checks
4. Symlink resolution guard

### Access Control Lists (ACL)

Document-level access control:

```python
# During ingest
engine.ingest("./confidential", metadata={
    "acl_roles": ["admin", "finance"],
    "acl_users": ["user123"],
})

# During query — only returns documents matching user's roles
result = engine.query(
    "What is the budget?",
    filters={"acl_roles": ["finance"]},
)
```

### Rate Limiting

Token bucket rate limiting per API key:

```yaml
# Configured via API server middleware
```

### Request Tracking

Every API request gets a unique `X-Request-ID` header for tracing.

---

## Batch Processing

Process multiple queries in parallel with controlled concurrency:

```python
from quantumrag.core.batch import BatchProcessor

processor = BatchProcessor(engine, max_concurrency=5)

queries = [
    "What is the revenue?",
    "Who is the CEO?",
    "List all products",
]

results = await processor.process(queries)
for query, result in zip(queries, results):
    print(f"Q: {query}")
    print(f"A: {result.answer}\n")
```

---

## Streaming

### Python SDK Streaming

```python
async for token in engine.query_stream("Summarize the report"):
    print(token, end="", flush=True)
```

### SSE Streaming (API)

```bash
curl -N -X POST http://localhost:8000/v1/query/stream \
  -H "Content-Type: application/json" \
  -d '{"query": "Summarize the report"}'
```

Response (Server-Sent Events):

```
data: The
data: report
data: shows
data: ...
data: [DONE]
```

---

## Conversation Mode

Multi-turn conversations with automatic context tracking:

```python
from quantumrag.core.models import ConversationTurn

history = []

# Turn 1
result = engine.query("Who is the CTO?")
history.append(ConversationTurn(role="user", content="Who is the CTO?"))
history.append(ConversationTurn(role="assistant", content=result.answer))

# Turn 2 — "그분의" (that person's) resolved to CTO
result = engine.query(
    "그분의 이전 경력은?",
    conversation_history=history,
)
```

The engine automatically:
1. Rewrites queries with pronoun resolution
2. Tracks active topic across turns
3. Augments ambiguous queries with conversation context
