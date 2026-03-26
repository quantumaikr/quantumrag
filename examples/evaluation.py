"""QuantumRAG Evaluation Example.

This example shows how to run QuantumRAG's built-in evaluation system
to measure retrieval and generation quality.

Usage:
    1. Install QuantumRAG:
        pip install quantumrag[all]
    2. Set your API key (or use Ollama for local models):
        export OPENAI_API_KEY=your-key
    3. Prepare some documents in a ./docs directory.
    4. Run this script:
        python examples/evaluation.py

The evaluation pipeline will:
    - Ingest sample documents
    - Auto-generate synthetic QA pairs from the ingested content
    - Run each question through the engine
    - Compute metrics: retrieval recall, faithfulness, answer relevancy,
      token F1, and latency
    - Print a report with scores and improvement suggestions
"""

import asyncio
from pathlib import Path

from quantumrag import Engine
from quantumrag.core.config import QuantumRAGConfig
from quantumrag.core.evaluate import Evaluator


async def main() -> None:
    # 1. Create config and engine
    config = QuantumRAGConfig.default(
        project_name="eval-demo",
        storage={
            "backend": "local",
            "vector_db": "lancedb",
            "document_store": "sqlite",
            "data_dir": "./eval_demo_data",
        },
    )
    engine = Engine(config=config)

    # 2. Ingest sample documents
    docs_path = Path("./docs")
    if docs_path.exists():
        result = engine.ingest(docs_path)
        print(f"Ingested {result.documents} documents, {result.chunks} chunks")
    else:
        print(f"Directory {docs_path} not found. Create it and add some text files.")
        raise SystemExit(1)

    # 3. Run evaluation (auto-generates synthetic QA pairs)
    evaluator = Evaluator(engine)
    eval_result = await evaluator.evaluate(sample_count=10)

    # 4. Print results
    print(f"\n{'=' * 60}")
    print(f"Evaluation Summary: {eval_result.summary}")
    print(f"{'=' * 60}")

    for metric in eval_result.metrics:
        passed = metric.details.get("passed", "N/A")
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {metric.name}: {metric.score:.4f}")

    # 5. Print improvement suggestions
    if eval_result.suggestions:
        print(f"\n{'=' * 60}")
        print("Suggestions:")
        for suggestion in eval_result.suggestions:
            print(f"  - {suggestion}")

    # Optional: evaluate against a pre-built benchmark file
    # eval_result = await evaluator.evaluate(benchmark_file="benchmark.json")


if __name__ == "__main__":
    asyncio.run(main())
