"""QuantumRAG with Local Ollama Models (No API Keys Needed).

This example shows how to use QuantumRAG entirely with local models
served by Ollama, so you don't need any cloud API keys.

Setup instructions:
    1. Install Ollama: https://ollama.com/download
    2. Pull models:
        ollama pull nomic-embed-text
        ollama pull llama3.2
    3. Install QuantumRAG:
        pip install quantumrag[all]
    4. Run this script:
        python examples/local_ollama.py
"""

from pathlib import Path

from quantumrag import Engine
from quantumrag.core.config import QuantumRAGConfig

# Configure QuantumRAG to use Ollama for all model calls.
config = QuantumRAGConfig.default(
    project_name="local-ollama-demo",
    models={
        "embedding": {
            "provider": "ollama",
            "model": "nomic-embed-text",
            "dimensions": 768,
        },
        "generation": {
            "simple": {"provider": "ollama", "model": "llama3.2"},
            "medium": {"provider": "ollama", "model": "llama3.2"},
            "complex": {"provider": "ollama", "model": "llama3.2"},
        },
        "reranker": {"provider": "flashrank"},
        "hype": {
            "provider": "ollama",
            "model": "llama3.2",
            "questions_per_chunk": 3,
        },
    },
    storage={
        "backend": "local",
        "vector_db": "lancedb",
        "document_store": "sqlite",
        "data_dir": "./ollama_demo_data",
    },
)

# Create the engine with the local config.
engine = Engine(config=config)

# Ingest documents from a directory (or a single file).
docs_path = Path("./docs")
if docs_path.exists():
    result = engine.ingest(docs_path)
    print(f"Ingested {result.documents} documents, {result.chunks} chunks")
else:
    print(f"Directory {docs_path} not found. Create it and add some text files.")
    print("Example: echo 'QuantumRAG is a RAG engine.' > docs/sample.txt")
    raise SystemExit(1)

# Ask a question -- all inference runs locally via Ollama.
answer = engine.query("What are the key topics in these documents?")
print(f"\nAnswer: {answer.answer}")
print(f"Confidence: {answer.confidence.value}")

# Show sources
for i, source in enumerate(answer.sources, 1):
    title = source.document_title or source.chunk_id[:12]
    print(f"\n[{i}] {title}")
    print(f"    {source.excerpt[:100]}...")
