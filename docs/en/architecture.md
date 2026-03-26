# Architecture

> How QuantumRAG processes documents and answers questions.

QuantumRAG follows an **Index-Heavy, Query-Light** philosophy: expensive computation happens once during document ingestion, enabling fast and accurate queries at runtime.

---

## High-Level Overview

```
                          ┌──────────────────────────────────────┐
                          │            QuantumRAG Engine          │
                          │           (Single Entry Point)        │
                          └─────────┬────────────────┬───────────┘
                                    │                │
                     ┌──────────────▼──┐      ┌──────▼──────────────┐
                     │  Ingest Pipeline │      │   Query Pipeline    │
                     │  (Index-Heavy)   │      │   (Query-Light)     │
                     └──────────────┬──┘      └──────┬──────────────┘
                                    │                │
              ┌─────────────────────▼────────────────▼─────────────────┐
              │                    Storage Layer                        │
              │  SQLite (documents)  LanceDB (vectors)  Tantivy (BM25) │
              └────────────────────────────────────────────────────────┘
```

---

## Ingest Pipeline

The ingest pipeline transforms raw documents into a rich, multi-layered index optimized for retrieval.

### Step-by-Step Flow

```
Documents (PDF, DOCX, HWP, XLSX, ...)
  │
  ▼
1. Parse ──────────── Format-specific parsers (9 formats)
  │
  ▼
2. Chunk ──────────── Auto-select strategy (structural → semantic → fixed)
  │
  ▼
3. Profile ────────── Document signal extraction (domain, structure, language)
  │
  ▼
4. Preamble ───────── LLM-generated contextual prefix per chunk
  │
  ▼
5. Fact Extract ───── Rule-based domain fact extraction (6 domains)
  │
  ▼
6. Quality Check ──── Parse quality verification and filtering
  │
  ▼
7. 4-Level Indexing
  │  ├─ Level 1: Multi-Resolution Summaries (doc → section → chunk)
  │  ├─ Level 2: Structured Fact Index (entity, attribute, relation)
  │  ├─ Level 3: Derived Index Enrichment (synonyms, hierarchy → BM25)
  │  └─ Level 4: Entity-Centric Reverse Index (entity → chunk_ids)
  │
  ▼
8. Triple Index Build
  │  ├─ Original Embedding (text-embedding-3-small)
  │  ├─ HyPE Embedding (hypothetical questions → embeddings)
  │  └─ Contextual BM25 (Kiwi morphology tokenized terms)
  │
  ▼
9. Chunk Constellation Graph (sibling, parent, entity edges)
```

### Parsing

Supported formats with format-specific parsers:

| Format | Extensions | Parser |
|--------|-----------|--------|
| Plain Text | `.txt`, `.text`, `.log` | PlainTextParser |
| Markdown | `.md`, `.markdown` | MarkdownParser (extracts YAML frontmatter) |
| HTML | `.html`, `.htm` | HTMLParser (strips tags, normalizes) |
| CSV/TSV | `.csv`, `.tsv` | CSVParser (converts to structured text) |
| PDF | `.pdf` | PDFParser |
| Word | `.docx` | DocxParser |
| PowerPoint | `.pptx` | PptxParser |
| Excel | `.xlsx` | XlsxParser |
| HWP | `.hwp` | HWPParser (Korean government documents) |

Parser selection: extension-based lookup first, then MIME type detection via magic bytes.

### Chunking Strategies

| Strategy | When Used | Description |
|----------|-----------|-------------|
| **auto** (default) | Always | Auto-selects based on document structure |
| **structural** | Headings detected | Splits by Markdown/HTML headings, preserves hierarchy |
| **semantic** | Paragraph structure | Groups by semantic similarity, respects natural breaks |
| **fixed** | Fallback | Token-based splitting with sentence boundary respect |

Auto-selection logic:
1. Has Markdown/HTML headings → structural
2. Has paragraph structure (3+ double-newlines) → semantic
3. Otherwise → fixed

### 4-Level Indexing

**Level 1: Multi-Resolution Summaries**

Creates synthetic chunks at coarser granularities:
- **Document-level**: 1 per document — full overview
- **Section-level**: 1 per H2/breadcrumb group — section summaries
- **Chunk-level**: Original chunks unchanged

Rule-based summarization (no LLM cost): extracts key lines, lists entities/facts, severity/status distribution.

**Level 2: Structured Fact Extraction**

Rule-based extraction (regex, no LLM) across 6 domains:

| Domain | Extracted Facts | Example |
|--------|----------------|---------|
| Security | Issue IDs, severity, status | `SEC-001`, `severity:Critical`, `status:완료` |
| Finance | Metrics, fund allocations | `매출 150억`, `R&D: 80억원` |
| HR | Team info, headcount, leaders | `AI팀 15명`, `팀장: 김철수` |
| Product | Versions, releases, changelogs | `v2.4.0`, release date |
| Patent | Patent IDs, inventors, status | `PAT-003`, inventors list |
| Contract | Customer, tier, deployment | `고객: A사`, `tier:Enterprise` |

Facts stored in `chunk.metadata["facts"]` as structured dicts.

**Level 3: Derived Index Enrichment**

Generates additional BM25 searchable terms at ingest time:

| Pattern | Generated Terms |
|---------|----------------|
| severity:Critical | "High 이상", "Medium 이상" (hierarchy) |
| Date 2024-07-20 | "하반기", "Q3", "2024년 Q3" (temporal) |
| Amount 3.2억 | "약 3억", "억 단위" (normalization) |
| status:완료 | "조치 완료된", "해결됨" (synonyms) |
| Version v2.4.0 | "v2.4", "2.4 버전" (normalization) |

**Level 4: Entity-Centric Reverse Index**

In-memory reverse index: `entity_key → set[chunk_id]`

Index types:
- Pattern entities: `SEC-001`, `PAT-003`, `v2.5.0` (uppercased)
- Attribute entities: `severity:Critical`, `status:완료`, `tier:Enterprise`
- Severity hierarchy: Critical also indexed under `severity_gte:High`, `severity_gte:Medium`
- Fund allocations: `type:fund_allocation`, `fund_item:{name}`
- Named entities: `person:{name}`, `customer:{name}`

### Triple Index

Three parallel search indexes built from the same chunks:

| Index | How Built | What It Captures |
|-------|-----------|-----------------|
| **Original Embedding** | Embed `chunk.content` directly | Semantic similarity |
| **HyPE Embedding** | Generate N hypothetical questions per chunk → embed questions | Question-question matching |
| **Contextual BM25** | Prepend contextual prefix → Kiwi tokenize → index | Keyword overlap + morphology |

HyPE (Hypothetical Prompt Embedding) bridges the query-document embedding gap: instead of comparing a question to a passage, it compares a question to other questions, which live in a similar embedding space.

### Chunk Constellation Graph

Pre-computed relationship network:

| Edge Type | Description | Weight |
|-----------|-------------|--------|
| Sibling | Adjacent chunks from same document | 1.0 |
| Parent Section | Chunks sharing same heading/breadcrumb | 0.8 |
| Entity Cross-Ref | Chunks mentioning same named entity | 0.6 |

At query time, BFS traversal with weight decay expands initial results to related chunks.

---

## Query Pipeline

The query pipeline transforms a user question into a grounded, cited answer.

### Step-by-Step Flow

```
User Query
  │
  ▼
1. Conversation Rewrite ── Pronoun resolution if history exists
  │
  ▼
2. Query Expansion ──────── Colloquial → formal rewriting
  │
  ▼
3. Classification ─────────  SIMPLE / MEDIUM / COMPLEX routing
  │
  ▼
4. Decomposition ──────────  Split compound queries into sub-queries
  │
  ▼
5. Entity Detection ───────  Detect IDs, severity filters, status filters
  │
  ▼
6. Triple Index Fusion Search
  │  ├─ Original Embedding search
  │  ├─ HyPE Embedding search
  │  └─ BM25 keyword search
  │  └─ Reciprocal Rank Fusion (RRF)
  │
  ▼
7. Entity Index Injection ── Merge guaranteed-recall chunks
  │
  ▼
8. Sibling Expansion ────── Add related chunks from constellation graph
  │
  ▼
9. Reranking ──────────────  Cross-encoder precision scoring
  │
  ▼
10. MMR Diversity ─────────  Reduce redundancy in results
  │
  ▼
11. Compression ───────────  Extractive, query-aware sentence selection
  │
  ▼
12. Generation ────────────  Source-grounded answer with [1][2] citations
  │
  ▼
13. Self-Correction ───────  Retry with broader search if insufficient
  │
  ▼
14. Map-Reduce ────────────  Aggregate if enumeration/counting detected
  │
  ▼
Answer + Sources + Confidence
```

### Adaptive Query Routing

| Complexity | Triggers | Model Tier | Pipeline |
|-----------|----------|------------|----------|
| **SIMPLE** | Short factual questions | nano | Fusion → Generate |
| **MEDIUM** | How/why, long queries, temporal | mini | Fusion → Rerank → Generate |
| **COMPLEX** | Comparative, multi-question, conditional | full | Full pipeline with decomposition |

### Triple Index Fusion (RRF)

Reciprocal Rank Fusion combines results from three indexes:

```
RRF_score(doc) = Σ (weight_i / (k + rank_i))
```

- `k = 60` (smoothing constant)
- Weights: Original 0.4, HyPE 0.35, BM25 0.25
- Candidates: `top_k × fusion_candidate_multiplier` per index
- Final scores normalized to [0, 1]

### Entity Injection

When entity patterns are detected in a query (e.g., "SEC-001", "severity >= High"):

1. Entity detector parses constraints from query
2. Entity reverse index returns matching chunk IDs
3. **Missing chunks** are injected into retrieval results
4. **Compressed chunks** are replaced with full content (prevents data loss from extractive compression)

### Map-Reduce RAG

Triggered for aggregation queries ("모두 나열", "전체 목록"):

1. Retrieve broad set (20+ chunks)
2. **Map phase**: Extract relevant facts from each chunk independently
3. **Reduce phase**: Aggregate extracted facts into final answer
4. Returns `STRONGLY_SUPPORTED` confidence

### Self-Corrective RAG

If initial generation returns `INSUFFICIENT_EVIDENCE`:

1. Extract missing focus from initial answer
2. Retry with focus-specific query and doubled `top_k`
3. Merge original + retry chunks
4. Re-generate with expanded context

---

## Storage Layer

| Component | Backend | Purpose |
|-----------|---------|---------|
| **Document Store** | SQLite | Documents, chunks, metadata |
| **Vector Store** | LanceDB | Embedding similarity search |
| **BM25 Store** | Tantivy | Full-text keyword search |

All storage is local by default (no external services required). Storage backends are pluggable via factory pattern.

---

## Data Flow Summary

```
                  Ingest (heavy)                    Query (light)
                  ────────────                      ─────────────
Documents ──► Parse ──► Chunk ──► Index         Query ──► Route ──► Search
                           │                                   │
                    ┌──────┴──────┐                    ┌───────┴────────┐
                    │  4-Level    │                    │ Triple Fusion  │
                    │  Indexing   │                    │ + Entity Index │
                    └──────┬──────┘                    └───────┬────────┘
                           │                                   │
                    ┌──────▼──────┐                    ┌───────▼────────┐
                    │ Triple Index│                    │  Rerank + MMR  │
                    │   Build     │                    │  + Compress    │
                    └──────┬──────┘                    └───────┬────────┘
                           │                                   │
                    ┌──────▼──────┐                    ┌───────▼────────┐
                    │   Storage   │◄──────────────────►│   Generation   │
                    │ SQLite/Lance│                    │  + Confidence  │
                    │ DB/Tantivy  │                    │  + Citations   │
                    └─────────────┘                    └────────────────┘
```
