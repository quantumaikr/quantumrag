"""Debug retrieval for specific failing queries.

Usage: .venv/bin/python datasets/debug_retrieval.py "query text here"
"""

import asyncio
import os
import sys
from pathlib import Path

# Fix path
_script_dir = str(Path(__file__).resolve().parent)
_project_root = str(Path(__file__).resolve().parent.parent)
if _script_dir in sys.path:
    sys.path.remove(_script_dir)
try:
    import datasets as _hf_datasets  # noqa: F401
except ImportError:
    pass
sys.path.insert(0, _script_dir)

# Load .env
env_path = Path(_project_root) / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

from quantumrag.core.config import QuantumRAGConfig
from quantumrag.core.engine import Engine


async def debug_query(query: str, data_dir: str) -> None:
    cfg = QuantumRAGConfig.default(storage={"data_dir": data_dir})
    # Match Combined QA runner: use local embeddings (1024d)
    cfg.models.embedding.provider = "local"
    cfg.models.embedding.model = "BAAI/bge-m3"
    cfg.models.embedding.dimensions = 1024
    engine = Engine(config=cfg)
    engine._ensure_initialized()

    # Get the fusion retriever components
    doc_store = engine._get_document_store()
    total_chunks = await doc_store.count_chunks()
    total_docs = await doc_store.count_documents()
    print(f"\n=== Corpus: {total_docs} docs, {total_chunks} chunks ===")
    print(f"=== Query: {query} ===\n")

    # Run full query with trace
    result = await engine.aquery(query, top_k=10)

    print(f"Confidence: {result.confidence.value}")
    print(f"Latency: {result.metadata.get('total_latency_ms', 0):.0f}ms")
    print(f"Path: {result.metadata.get('path', '?')}")
    print(f"\n--- Answer (first 300 chars) ---")
    print(result.answer[:300])

    print(f"\n--- Sources ({len(result.sources)}) ---")
    for i, s in enumerate(result.sources, 1):
        print(f"  [{i}] {s.document_title} — {s.section or ''} (score={s.relevance_score:.3f})")
        print(f"      excerpt: {s.excerpt[:120]}...")

    print(f"\n--- Trace ({len(result.trace)} steps) ---")
    for step in result.trace:
        lat = step.latency_ms
        lat_str = f"{lat:.0f}ms" if lat < 1000 else f"{lat/1000:.1f}s"
        print(f"  {step.step:30s} {lat_str:>8s}  {step.result[:80]}")
        if step.details:
            for k, v in step.details.items():
                val_str = str(v)[:60]
                print(f"    {k}: {val_str}")


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "Singleton 패턴은 어떤 역할을 하나요?"
    data_dir = str(Path(__file__).resolve().parent / ".combined" / ".rag_data")

    if not Path(data_dir).exists():
        print(f"ERROR: Combined QA data not found at {data_dir}")
        print("Run: .venv/bin/python datasets/run_qa_combined.py  (to build index first)")
        sys.exit(1)

    asyncio.run(debug_query(query, data_dir))
