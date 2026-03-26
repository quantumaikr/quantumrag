# Getting Started

> From installation to your first query in under 5 minutes.

---

## Installation

### Basic Installation

```bash
pip install quantumrag
```

### Recommended (All Features)

```bash
pip install quantumrag[all]
```

This installs all optional dependencies: OpenAI, Anthropic, LanceDB, Tantivy, Kiwi, FastAPI, etc.

### Selective Installation

```bash
# Korean language support
pip install quantumrag[korean]

# API server only
pip install quantumrag[api]

# Gemini provider
pip install quantumrag[gemini]

# Reranking models
pip install quantumrag[rerank]
```

### Development

```bash
git clone https://github.com/quantumrag/quantumrag.git
cd quantumrag
pip install -e ".[dev,all]"
```

---

## System Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| Python | 3.10 | 3.11 or 3.12 |
| RAM | 2 GB | 4 GB+ |
| GPU | Not required | Not required |
| Storage | SQLite + LanceDB + Tantivy (local) | Same |
| OS | Linux, macOS, Windows (WSL2) | Any |

---

## API Keys

QuantumRAG needs an LLM provider API key. Set it via environment variable:

```bash
# OpenAI (default provider)
export OPENAI_API_KEY=sk-...

# Or Anthropic
export ANTHROPIC_API_KEY=sk-ant-...

# Or Google Gemini
export GOOGLE_API_KEY=AIza...
```

For local models via Ollama, no API key is needed.

---

## Quick Start

### 1. Initialize a Project

```bash
quantumrag init
```

This creates a `quantumrag.yaml` config file with sensible defaults.

### 2. Ingest Documents

**CLI:**

```bash
quantumrag ingest ./docs --recursive
```

**Python:**

```python
from quantumrag import Engine

engine = Engine()
result = engine.ingest("./docs")
print(f"Indexed {result.documents} documents, {result.chunks} chunks")
```

### 3. Ask Questions

**CLI:**

```bash
quantumrag query "What is the quarterly revenue?"
```

**Python:**

```python
result = engine.query("What is the quarterly revenue?")
print(result.answer)       # Answer with inline citations [1], [2]
print(result.confidence)   # STRONGLY_SUPPORTED / PARTIALLY_SUPPORTED / INSUFFICIENT_EVIDENCE
print(result.sources)      # List of source references
```

### 4. Start the API Server (Optional)

```bash
quantumrag serve --port 8000
```

Then query via HTTP:

```bash
curl -X POST http://localhost:8000/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the quarterly revenue?"}'
```

---

## Using Local Models (No API Key)

Install [Ollama](https://ollama.com/) and pull models:

```bash
ollama pull nomic-embed-text
ollama pull llama3.2
```

Then configure QuantumRAG:

```python
from quantumrag import Engine

engine = Engine(
    embedding_model="nomic-embed-text",
    generation_model="llama3.2",
)
engine.ingest("./docs")
result = engine.query("Summarize the documents")
```

Or via YAML config:

```yaml
# quantumrag.yaml
models:
  embedding:
    provider: "ollama"
    model: "nomic-embed-text"
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
```

---

## Using Korean-Optimized Local Embeddings

For Korean documents without an API key:

```yaml
models:
  embedding:
    provider: "local"
    model: "BAAI/bge-m3"
    dimensions: 1024
```

This downloads and runs the BGE-M3 model locally (CPU-based, multilingual).

---

## Configuration

QuantumRAG uses a layered configuration system:

```
defaults ← quantumrag.yaml ← environment variables ← code arguments
```

### Config File

```bash
quantumrag init  # Generates quantumrag.yaml with defaults
```

### Environment Variables

All config keys can be overridden with `QUANTUMRAG_` prefix:

```bash
export QUANTUMRAG_LANGUAGE=ko
export QUANTUMRAG_RETRIEVAL__TOP_K=10
export QUANTUMRAG_MODELS__EMBEDDING__PROVIDER=gemini
```

### Code Arguments

```python
from quantumrag import Engine
from quantumrag.core.config import QuantumRAGConfig

# From YAML
engine = Engine(config="./quantumrag.yaml")

# With overrides
config = QuantumRAGConfig.from_yaml("./quantumrag.yaml", language="en")
engine = Engine(config=config)

# Quick overrides
engine = Engine(embedding_model="text-embedding-3-large", data_dir="./my_data")
```

---

## Verifying the Installation

```python
from quantumrag import Engine

engine = Engine()
status = engine.status()
print(status)
# {'documents': 0, 'chunks': 0, 'config': {...}, 'data_dir': './quantumrag_data'}
```

---

## Next Steps

- [Configuration Guide](configuration.md) — Full config reference
- [Architecture](architecture.md) — How the engine works internally
- [API Reference](api-reference.md) — HTTP API endpoints
- [Korean Guide](korean-support.md) — Korean language optimization
