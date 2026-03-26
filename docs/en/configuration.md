# Configuration Guide

> Complete reference for all QuantumRAG configuration options.

---

## Configuration Merge Order

```
defaults ← YAML file ← environment variables ← code arguments
```

Each layer overrides the previous. Environment variables use the `QUANTUMRAG_` prefix with `__` for nesting:

```bash
export QUANTUMRAG_LANGUAGE=ko
export QUANTUMRAG_MODELS__EMBEDDING__PROVIDER=gemini
export QUANTUMRAG_RETRIEVAL__TOP_K=10
```

---

## Full Reference

### Project Settings

```yaml
project_name: "my-knowledge-base"   # Project identifier
language: "ko"                       # Primary language: ko, en, auto
domain: "general"                    # Domain hint: general, legal, medical, financial, technical, support
```

### Models

#### Embedding

```yaml
models:
  embedding:
    provider: "openai"               # openai, gemini, ollama, local
    model: "text-embedding-3-small"  # Model name
    dimensions: 1536                 # Embedding dimensions
    api_key: null                    # null → uses SDK default env var
    base_url: null                   # Custom endpoint (Azure, etc.)
```

**Provider options:**

| Provider | Model | Dimensions | API Key Env Var |
|----------|-------|-----------|----------------|
| openai | text-embedding-3-small | 1536 | `OPENAI_API_KEY` |
| openai | text-embedding-3-large | 3072 | `OPENAI_API_KEY` |
| gemini | (Google Embedding API) | varies | `GOOGLE_API_KEY` |
| ollama | nomic-embed-text | 768 | (none) |
| local | BAAI/bge-m3 | 1024 | (none) |

#### Generation

Three tiers for cost optimization. Simple queries (~70%) use cheap models, complex queries (~10%) use powerful ones.

```yaml
models:
  generation:
    simple:
      provider: "openai"
      model: "gpt-5.4-nano"
      api_key: null
      base_url: null
    medium:
      provider: "openai"
      model: "gpt-5.4-mini"
      api_key: null
      base_url: null
    complex:
      provider: "anthropic"
      model: "claude-sonnet-4-20250514"
      api_key: null
      base_url: null
```

**Supported providers:** `openai`, `anthropic`, `gemini`, `ollama`

#### Reranker

```yaml
models:
  reranker:
    provider: "flashrank"            # flashrank, bge, cohere, jina, noop
    model: null                      # Provider-specific model override
```

| Provider | Cost | GPU | Notes |
|----------|------|-----|-------|
| flashrank | Free | CPU | Default. ms-marco-MiniLM-L-12-v2 |
| bge | Free | CPU | Multilingual support |
| cohere | Paid API | N/A | rerank-v3.5. Needs `COHERE_API_KEY` |
| jina | Paid API | N/A | jina-reranker-v2-base-multilingual. Needs `JINA_API_KEY` |
| noop | Free | N/A | Skip reranking (just trim to top_k) |

#### HyPE (Hypothetical Prompt Embedding)

```yaml
models:
  hype:
    provider: "openai"
    model: "gpt-5.4-nano"
    questions_per_chunk: 3           # Hypothetical questions per chunk
    api_key: null
    base_url: null
```

### Ingest Settings

```yaml
ingest:
  chunking:
    strategy: "auto"                 # auto, semantic, fixed, custom
    chunk_size: 512                  # Token count per chunk
    overlap: 50                      # Overlap tokens between chunks
  quality_check: true                # Verify parse quality after chunking
  contextual_preamble: true          # LLM-generated context prefix per chunk
```

| Strategy | Description |
|----------|-------------|
| auto | Auto-selects based on document structure (heading → structural, paragraphs → semantic, else → fixed) |
| structural | Splits by Markdown/HTML headings, preserves hierarchy |
| semantic | Groups by semantic similarity, respects natural breaks |
| fixed | Token-based splitting with sentence boundary respect |

### Retrieval Settings

```yaml
retrieval:
  top_k: 7                          # Number of chunks to retrieve
  fusion_candidate_multiplier: 3    # Candidates per index = top_k × multiplier
  fusion_weights:
    original: 0.4                   # Original embedding weight in RRF
    hype: 0.35                      # HyPE embedding weight in RRF
    bm25: 0.25                      # BM25 keyword weight in RRF
  rerank: true                      # Enable cross-encoder reranking
  compression: true                 # Enable context compression
  slow_retrieval_threshold_ms: 2000 # Warning threshold for slow queries
```

### Generation Settings

```yaml
generation:
  streaming: true                    # Token-by-token streaming
  max_tokens: 2048                   # Max tokens in generated answer
  temperature: 0.1                   # Generation temperature (0 = deterministic)
  citation_style: "inline"          # inline ([1], [2]) or footnote
  confidence_signal: true            # Include confidence assessment
  high_confidence_threshold: 0.8     # Score above this = STRONGLY_SUPPORTED
  low_confidence_threshold: 0.5      # Score above this = PARTIALLY_SUPPORTED
  no_answer_penalty: 0.3            # Confidence multiplier for INSUFFICIENT_EVIDENCE
  max_context_chars: 12000           # Max characters in context window
```

### Evaluation Settings

```yaml
evaluation:
  auto_synthetic: true               # Auto-generate QA pairs for evaluation
  metrics:
    - "retrieval_recall"
    - "faithfulness"
    - "answer_relevancy"
    - "completeness"
    - "latency"
    - "cost"
```

### Storage Settings

```yaml
storage:
  backend: "local"                   # local, server, cluster
  vector_db: "lancedb"              # lancedb, qdrant, pgvector
  document_store: "sqlite"          # sqlite, postgresql
  data_dir: "./quantumrag_data"     # Data directory path
```

### Cost Settings

```yaml
cost:
  budget_daily: null                 # Daily budget cap in USD (null = unlimited)
  budget_monthly: null               # Monthly budget cap in USD
  semantic_cache: false              # Enable semantic result caching
  prompt_caching: true               # Use provider-level prompt caching
```

### Korean Settings

```yaml
korean:
  morphology: "kiwi"                # kiwi (recommended) or mecab
  hwp_parser: "auto"                # auto, pyhwp, libreoffice
  mixed_script: true                # Korean-English mixed text handling
```

---

## API Key Configuration

Three ways to set API keys (in priority order):

### 1. YAML Config (Per-Model)

```yaml
models:
  embedding:
    api_key: "sk-..."
  generation:
    complex:
      api_key: "sk-ant-..."
```

### 2. QuantumRAG Environment Variables

```bash
export QUANTUMRAG_MODELS__EMBEDDING__API_KEY=sk-...
export QUANTUMRAG_MODELS__GENERATION__COMPLEX__API_KEY=sk-ant-...
```

### 3. SDK Default Environment Variables

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export GOOGLE_API_KEY=AIza...
export COHERE_API_KEY=...
export JINA_API_KEY=...
```

---

## Example Configurations

### Minimal (OpenAI Only)

```yaml
project_name: "my-project"
language: "auto"
```

Just set `OPENAI_API_KEY` and everything uses OpenAI defaults.

### Korean-Optimized

```yaml
project_name: "korean-docs"
language: "ko"
domain: "financial"

models:
  embedding:
    provider: "openai"
    model: "text-embedding-3-small"
  generation:
    simple:
      provider: "openai"
      model: "gpt-5.4-nano"
    complex:
      provider: "anthropic"
      model: "claude-sonnet-4-20250514"

korean:
  morphology: "kiwi"
  hwp_parser: "auto"
  mixed_script: true
```

### Fully Local (No API Keys)

```yaml
project_name: "offline-project"
language: "auto"

models:
  embedding:
    provider: "local"
    model: "BAAI/bge-m3"
    dimensions: 1024
  generation:
    simple:
      provider: "ollama"
      model: "llama3.2"
    medium:
      provider: "ollama"
      model: "llama3.2"
    complex:
      provider: "ollama"
      model: "llama3.2"
  reranker:
    provider: "flashrank"
  hype:
    provider: "ollama"
    model: "llama3.2"
    questions_per_chunk: 2
```

### Cost-Optimized

```yaml
project_name: "budget-project"

models:
  generation:
    simple:
      provider: "openai"
      model: "gpt-5.4-nano"
    medium:
      provider: "openai"
      model: "gpt-5.4-nano"
    complex:
      provider: "openai"
      model: "gpt-5.4-mini"

retrieval:
  top_k: 5
  rerank: false
  compression: true

cost:
  budget_monthly: 50.0
  prompt_caching: true

ingest:
  contextual_preamble: false
```

---

## Programmatic Configuration

```python
from quantumrag import Engine
from quantumrag.core.config import QuantumRAGConfig

# From YAML with overrides
config = QuantumRAGConfig.from_yaml("quantumrag.yaml", language="en")

# Pure code
config = QuantumRAGConfig.default(
    language="ko",
    domain="financial",
)

# Export to YAML
config.to_yaml("output.yaml")

# Use with Engine
engine = Engine(config=config)
```
