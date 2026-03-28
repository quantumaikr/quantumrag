"""End-to-end Engine test: ingest real docs → query with real LLM APIs.

Usage:
    uv run python tests/run_engine_e2e.py
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

# Load .env
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

from quantumrag.core.config import QuantumRAGConfig
from quantumrag.core.engine import Engine

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
DIVIDER = "=" * 70

# Use a temp data directory
DATA_DIR = Path(__file__).resolve().parent.parent / "test_quantumrag_data"
DOCS_DIR = Path(__file__).resolve().parent.parent / "test_docs"


def main() -> None:
    print(DIVIDER)
    print("QuantumRAG — End-to-End Engine Test")
    print(DIVIDER)

    # Clean previous data
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)

    config = QuantumRAGConfig.default(
        storage={"data_dir": str(DATA_DIR)},
    )

    print(f"\n  Provider: {config.models.embedding.provider} / {config.models.embedding.model}")
    print(
        f"  LLM (simple): {config.models.generation.simple.provider} / {config.models.generation.simple.model}"
    )
    print(f"  Data dir: {DATA_DIR}")
    print(f"  Docs dir: {DOCS_DIR}")

    engine = Engine(config=config)

    # ── Step 1: Ingest ──────────────────────────────────────────────────
    print(f"\n{'─' * 40}")
    print("Step 1: Ingest documents")
    print(f"{'─' * 40}")

    t0 = time.perf_counter()
    result = engine.ingest(DOCS_DIR)
    elapsed = time.perf_counter() - t0

    print(f"  Documents: {result.documents}")
    print(f"  Chunks: {result.chunks}")
    print(f"  Time: {elapsed:.1f}s")
    if result.errors:
        print(f"  Errors: {result.errors}")

    if result.documents > 0 and result.chunks > 0:
        print(f"  {PASS} Ingest successful")
    else:
        print(f"  {FAIL} No documents ingested")
        return

    # ── Step 2: Query ───────────────────────────────────────────────────
    questions = [
        ("퀀텀소프트의 매출은 얼마인가요?", "152억"),
        ("재택근무는 주 몇 회 가능한가요?", "2"),
        ("Series B 투자 금액은?", "120억"),
        ("점심 식대는 얼마나 지원되나요?", "12,000"),
        ("대표이사 이름은?", "김태현"),
    ]

    print(f"\n{'─' * 40}")
    print("Step 2: Query (5 questions)")
    print(f"{'─' * 40}")

    passed = 0
    for i, (question, expected_keyword) in enumerate(questions, 1):
        t0 = time.perf_counter()
        try:
            qresult = engine.query(question)
            elapsed = time.perf_counter() - t0
            answer = qresult.answer
            confidence = qresult.confidence.value

            has_keyword = expected_keyword in answer
            status = PASS if has_keyword else FAIL
            if has_keyword:
                passed += 1

            print(f"\n  Q{i}: {question}")
            print(f"  A: {answer[:150]}{'...' if len(answer) > 150 else ''}")
            print(f"  Confidence: {confidence} | Latency: {elapsed:.1f}s | {status}")
            if qresult.sources:
                print(f"  Sources: {len(qresult.sources)} chunks")
                for src in qresult.sources[:2]:
                    title = src.document_title or "?"
                    print(f"    - {title} (score={src.relevance_score:.2f})")

        except Exception as exc:
            elapsed = time.perf_counter() - t0
            print(f"\n  Q{i}: {question}")
            print(f"  {FAIL} Error: {exc!s:.200}")

    # ── Summary ─────────────────────────────────────────────────────────
    print(f"\n{DIVIDER}")
    print(f"Results: {passed}/{len(questions)} queries answered correctly")
    print(DIVIDER)

    # Cleanup
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
        print(f"\nCleaned up {DATA_DIR}")


if __name__ == "__main__":
    main()
