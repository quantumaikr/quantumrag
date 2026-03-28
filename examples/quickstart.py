"""QuantumRAG Quick Start Example.

This example shows the simplest way to use QuantumRAG:
1. Create an engine
2. Ingest documents
3. Ask questions

Requirements:
    pip install quantumrag[all]
    export OPENAI_API_KEY=your-key  # or any of: GOOGLE_API_KEY, ANTHROPIC_API_KEY
"""

from quantumrag import Engine

# Create engine — auto-detects your API key and selects optimal models
engine = Engine()

# Or use a local model via Ollama (no API key needed):
# engine = Engine(
#     embedding_model="nomic-embed-text",
#     generation_model="llama3.2",
# )

# Ingest documents from a directory
result = engine.ingest("./docs")
print(f"Ingested {result.documents} documents, {result.chunks} chunks")

# Ask a question
answer = engine.query("What is the main topic of these documents?")
print(f"\nAnswer: {answer.answer}")
print(f"Confidence: {answer.confidence.value}")

# Show sources
for i, source in enumerate(answer.sources, 1):
    print(f"\n[{i}] {source.document}")
    print(f"    {source.excerpt[:100]}...")

# Check engine status
status = engine.status()
print(f"\nDocuments indexed: {status['documents']}")
print(f"Chunks indexed: {status['chunks']}")
