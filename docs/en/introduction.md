# Introducing QuantumRAG

> Put documents in. Ask questions. Get cited answers.

---

## The Problem

Retrieval-Augmented Generation (RAG) has become the standard approach for building LLM-powered knowledge systems. Feed your documents into a vector database, embed a user's question, retrieve the top-K similar chunks, and pass them to an LLM to generate an answer. Simple, elegant, and — for anything beyond toy demos — deeply inadequate.

Here's what breaks in production:

**Embedding-only retrieval misses critical information.** A question about "security issues rated High or above" shares almost no semantic similarity with a chunk that says "SEC-003: SQL injection vulnerability discovered in auth module, severity Critical." Embedding search finds topically related passages, but not the precise data needed to answer the question.

**Korean is an afterthought.** Most RAG frameworks treat Korean as "just another language." But Korean's agglutinative morphology means BM25 keyword search fails without proper tokenization. The HWP document format — used by virtually every Korean government and corporate entity — is unsupported. EUC-KR encoded legacy files are silently corrupted.

**Query-time computation is a bottleneck.** The standard RAG pattern performs minimal work at indexing time (embed and store) and pushes all intelligence to query time (retrieve, rerank, generate). This means every query pays the full cost of understanding the document collection from scratch.

**Simple pipelines fail on real questions.** Real users ask compound questions ("What is the largest fund allocation item and how much is it?"), entity-specific queries ("List all security issues with severity High or above that have been resolved"), and cross-document questions ("Does the customer count in the board report match the sales pipeline data?"). A single embedding lookup followed by LLM generation cannot reliably answer any of these.

---

## The Design Philosophy

QuantumRAG's core promise is simple: **put documents in, ask questions, get accurate cited answers.**

This is possible because of the Index-Heavy, Query-Light architecture: **the more you understand your documents at indexing time, the less work you need to do at query time.**

Instead of treating documents as opaque text to be embedded, QuantumRAG builds a rich, multi-layered understanding of every document at ingest time:

- What entities and facts does this document contain?
- What are the key attributes — severity levels, status values, financial figures, version numbers?
- How do the chunks relate to each other — siblings, parent sections, shared entities?
- What questions could this chunk answer?
- What synonyms and hierarchical terms would help find this content?

This upfront investment pays for itself immediately. When a user asks "List all Critical and High severity security issues that have been resolved," the engine doesn't need to hope that embedding similarity captures the right chunks. It looks up `severity_gte:High` and `status:완료` in the Entity Reverse Index and returns the exact chunks — with 100% recall, in milliseconds.

---

## What Makes QuantumRAG Different

### 1. Triple Index Fusion

Most RAG systems use a single retrieval method — usually embedding similarity. QuantumRAG searches three indexes simultaneously and fuses the results:

| Index | What It Captures | Why It Matters |
|-------|-----------------|----------------|
| **Original Embedding** | Semantic meaning | Finds topically relevant passages |
| **HyPE Embedding** | Question-level semantics | Bridges the query-document gap by comparing questions to questions |
| **Contextual BM25** | Exact keywords + morphology | Catches entities, numbers, and technical terms that embeddings miss |

The three result sets are combined using Reciprocal Rank Fusion (RRF) with tuned weights (0.4 / 0.35 / 0.25). This hybrid approach consistently outperforms any single index.

**HyPE (Hypothetical Prompt Embedding)** deserves special mention. At indexing time, the engine generates hypothetical questions for each chunk — "What security vulnerability was found in SEC-003?", "What is the severity of the auth module issue?" — and embeds those questions. At query time, the user's question is compared to these pre-generated questions rather than to the raw document text. Since questions and questions live in a more similar embedding space than questions and passages, this dramatically improves retrieval for question-answering workloads.

### 2. 4-Level Indexing

Beyond the Triple Index, QuantumRAG builds four additional layers of understanding at ingest time:

**Level 1: Multi-Resolution Summaries.** Each document is summarized at three granularities — document-level, section-level, and chunk-level. When a user asks a broad question ("What is this report about?"), the document-level summary provides a direct answer without needing to stitch together individual chunks.

**Level 2: Structured Fact Extraction.** A rule-based extraction engine identifies entities, attributes, and relations across six domains — security, finance, HR, product, patents, and contracts. These structured facts enable precise filtering that embedding search alone cannot provide.

**Level 3: Derived Index Enrichment.** At indexing time, the engine generates additional searchable terms: severity hierarchies ("Critical" → also findable by "High 이상"), temporal normalizations (dates → "Q3", "하반기"), amount normalizations, and status synonyms. These terms are injected into the BM25 index, ensuring that Korean queries with different phrasing still find the right content.

**Level 4: Entity-Centric Reverse Index.** An in-memory reverse index maps entity keys (`SEC-001`, `severity:Critical`, `customer:Acme`) directly to chunk IDs. This guarantees 100% recall for entity-based queries — no embedding similarity threshold can cause a miss.

### 3. Adaptive Query Intelligence

Not every question needs the same pipeline. QuantumRAG classifies queries into complexity tiers and adapts its behavior:

- **Simple questions** (~70%) use a lightweight model, skip reranking, and return quickly
- **Medium questions** (~20%) add reranking and broader retrieval
- **Complex questions** (~10%) use full decomposition, entity detection, map-reduce aggregation, and the most capable model

This tiered approach reduces average cost by 60-70% compared to routing everything through a full-capability pipeline, while maintaining quality where it matters.

Additional adaptive behaviors:

- **Entity Detection**: When a query contains entity patterns ("SEC-001", "severity >= High", "status:완료"), the engine activates the Entity Reverse Index for guaranteed recall
- **Query Decomposition**: Compound questions are split into independent sub-queries, each retrieving its own context
- **Map-Reduce RAG**: Enumeration queries ("list all...", "모두 나열") trigger parallel extraction across many chunks, followed by aggregation
- **Self-Corrective RAG**: If the initial generation returns `INSUFFICIENT_EVIDENCE`, the engine automatically retries with a broader search
- **Broad Retrieval Patterns**: Superlative, comparative, and multi-constraint queries automatically expand the retrieval window

### 4. Korean as a First-Class Citizen

QuantumRAG was designed with Korean from the ground up, not bolted on as a plugin:

- **Kiwi Morphological Analysis** powers BM25 indexing. Korean is agglutinative — "보안이슈의심각도가높습니다" is one "word" by whitespace but contains four meaningful morphemes. Without proper tokenization, BM25 search is useless for Korean.
- **HWP/HWPX Parsing** handles the standard document format of Korean government and corporate organizations natively.
- **Korean Query Patterns** recognize severity ranges ("High 등급 이상"), status filters ("조치 완료된"), and enumeration requests ("모두 나열해주세요") using morphology-aware regex patterns.
- **Derived Korean Terms** ensure that "Critical" is findable by "심각", "High 이상", and "높음 등급" through ingest-time synonym generation.
- **Bilingual System Prompts** with 11 specialized Korean generation rules handle edge cases like competitor entity attribution and multi-source numerical discrepancies.

### 5. Production-Ready Infrastructure

QuantumRAG is not a notebook demo. It ships with the infrastructure needed for real deployments:

- **FastAPI Server** with SSE streaming, API key authentication, rate limiting, and path traversal protection
- **Plugin System** for extending every pipeline stage without forking the core
- **Multi-Tenancy** with isolated storage, per-tenant models, and quota enforcement
- **Semantic Cache** with exact and cosine-similarity matching to avoid redundant LLM calls
- **Structured Observability** via structlog with per-query tracing stored in SQLite
- **5 Data Connectors** — local filesystem, Google Drive, Notion, AWS S3, and web URLs
- **Built-in Evaluation** with 6 metrics, synthetic QA generation, and A/B configuration comparison

### 6. Zero Infrastructure Requirements

QuantumRAG runs entirely locally with zero external services:

- **SQLite** for document storage
- **LanceDB** for vector search
- **Tantivy** for BM25 full-text search
- **FlashRank** for CPU-based reranking (free, no GPU)
- **Ollama** for local LLM inference (optional)

No Docker, no Kubernetes, no managed vector database, no GPU. `pip install quantumrag[all]` and you're running.

---

## Validated Results

QuantumRAG is tested against **87 real-world scenario tests** across 16 categories, spanning 4 difficulty levels from simple factual lookups to extreme multi-constraint cross-document reasoning. Current pass rate: **86/87 (98.9%)**.

The test suite includes challenges that most RAG systems fail at:

- Multi-hop reasoning across 3+ documents
- Numerical calculations from scattered data points
- Entity-specific queries with severity and status constraints
- Implicit inference from information not directly stated
- Cross-document consistency verification
- Adversarial and edge case queries

These are not cherry-picked examples. The full test suite runs against the same engine configuration every time, with keyword-matching validation — no human grading.

---

## Three Ways to Use It

| | What you do | What happens |
|---|-------------|-------------|
| **Just use it** | `engine.ingest("./docs")` → `engine.query("...")` | Parser, chunker, index, routing — all auto-selected |
| **Tune it** | Adjust fusion weights, pick models, set domain | Better results for your specific use case |
| **Own it** | Custom parsers, chunkers, retrievers, generators | Every layer is replaceable via plugins |

Zero configuration to first answer. Full control when you need it.

---

## Who Is This For

**Enterprise teams** building internal knowledge systems over Korean and English corporate documents — board minutes, audit reports, contracts, patent filings, product changelogs.

**Developers** who need a RAG engine that works out of the box for Korean, without spending weeks on morphological analysis integration and HWP parsing.

**Teams** who want structured-data precision (entity lookups, attribute filtering) combined with the flexibility of semantic search, without building two separate systems.

**Developers who are not RAG experts** — who don't have time to assemble LangChain chains or design LlamaIndex pipelines, and just want an engine that works when you put documents in.

---

## Get Started

```bash
pip install quantumrag[all]
```

```python
from quantumrag import Engine

engine = Engine()
engine.ingest("./docs")
result = engine.query("How does the Triple Index Fusion work?")
print(result.answer)
```

Three lines. No configuration required. The rest is handled automatically.

For deeper exploration, see the [full documentation](index.md).
