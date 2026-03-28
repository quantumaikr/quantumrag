# Advanced Features

> Post-generation correction, hallucination prevention, semantic caching, observability, security, and batch processing.

---

## Post-Generation Correction Pipeline

After generating an answer, a modular correction chain runs automatically:

```
Generate → Retrieval Retry → Self-Correct → Fact Verify → Completeness
```

Each step checks preconditions and skips if not needed (zero overhead on happy path).

| Step | Trigger | Action |
|------|---------|--------|
| **Retrieval Retry** | confidence = insufficient_evidence | Re-retrieve with BM25-dominant strategy |
| **Self-Correct** | Low confidence patterns detected | Re-generate with correction hints |
| **Fact Verify** | Customer/financial facts in answer | Cross-check against extracted facts |
| **Completeness** | Multi-part query detected | Check all expected items are covered |

### Fact Verifier (Hallucination Prevention)

Zero-LLM-cost, rule-based verification:

```python
# At ingest time: facts are extracted and stored in chunk metadata
# At query time: answer entities are verified against those facts

result = engine.query("주요 고객사를 알려주세요")
# If answer mentions "SK텔레콤" but fact index only has "삼성전자", "LG전자"
# → fact_verifier flags it as potential hallucination
# → engine re-generates with correction hint
```

Design: precision over recall — only flags clear contradictions, not ambiguity. Single unknown entity is tolerated (conservative threshold).

### Completeness Checker

Detects multi-part queries and verifies coverage:

```python
# "3건의 계약을 알려주세요" → expects 3 items
# "매출과 비용 및 이익을 비교해줘" → expects 3 items: 매출, 비용, 이익
# If answer only covers 2/3, triggers targeted re-retrieval for missing items
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
result = engine.query("How does adaptive query routing work?")
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
    "How does the Triple Index Fusion work?",
    "What chunking strategies are available?",
    "List all supported data connectors",
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
