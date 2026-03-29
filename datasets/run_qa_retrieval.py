"""Retrieval-Only QA Test — zero LLM calls, measures retrieval precision.

Tests whether the correct source documents appear in retrieval results.
No generation, no post-correction — pure retrieval quality measurement.
Runs in < 30 seconds for all 105 questions.

Usage:
    .venv/bin/python datasets/run_qa_retrieval.py
"""

import asyncio
import hashlib
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

# --- Load .env ---
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

from quantumrag.core.config import QuantumRAGConfig
from quantumrag.core.engine import Engine

# --- Setup ---
ds_root = Path(__file__).resolve().parent
combined_dir = ds_root / ".combined"
sources_dir = combined_dir / "sources"
data_dir = combined_dir / ".rag_data"
hash_file = combined_dir / ".sources_hash"

CONCURRENCY = 10  # No LLM calls, can be aggressive
TOP_K = 10

# --- Collect datasets ---
datasets = sorted(ds_root.glob("ds-*"))
source_map: dict[str, str] = {}
all_questions: list[dict] = []

sources_dir.mkdir(parents=True, exist_ok=True)

for ds_path in datasets:
    ds_id = ds_path.name
    qa_path = ds_path / "qa.yaml"
    if not qa_path.exists():
        continue

    with open(qa_path) as f:
        qa = yaml.safe_load(f)

    src_dir = ds_path / "sources"
    if src_dir.exists():
        for src_file in sorted(src_dir.glob("*.md")):
            prefixed_name = f"{ds_id}_{src_file.name}"
            dest = sources_dir / prefixed_name
            shutil.copy2(src_file, dest)
            source_map[f"{ds_id}_{src_file.stem}"] = str(src_file)

    for q in qa.get("questions", []):
        remapped = dict(q)
        remapped["dataset"] = ds_id
        remapped["id"] = f"{ds_id}:{q['id']}"
        remapped["expected_sources"] = [f"{ds_id}_{sid}" for sid in q.get("source_ids", [])]
        all_questions.append(remapped)


# --- Ingest ---
def compute_sources_hash() -> str:
    h = hashlib.sha256()
    for f in sorted(sources_dir.glob("*")):
        if f.is_file():
            h.update(f.name.encode())
            h.update(f.read_bytes())
    return h.hexdigest()[:16]


current_hash = compute_sources_hash()
cached_hash = hash_file.read_text().strip() if hash_file.exists() else ""

config = QuantumRAGConfig.default(storage={"data_dir": str(data_dir)})
engine = Engine(config=config)

print("=" * 60)
print("  Retrieval-Only QA Test (zero LLM generation)")
print("=" * 60)
print(f"  Sources: {len(source_map)} | Questions: {len(all_questions)} | top_k: {TOP_K}")

if current_hash == cached_hash and data_dir.exists():
    print(f"  Ingest: cached (hash={current_hash})")
    engine.ingest(str(sources_dir), mode="fast")
else:
    if data_dir.exists():
        shutil.rmtree(data_dir)
    print(f"  Ingesting {len(source_map)} sources (mode=fast)...")
    t0 = time.perf_counter()
    engine.ingest(str(sources_dir), mode="fast")
    print(f"  Ingest: {time.perf_counter() - t0:.1f}s")
    hash_file.write_text(current_hash)


# --- Retrieval-only test ---
async def test_retrieval(q: dict) -> dict:
    """Run retrieval only (no generation) and check source recall."""
    expected_sources = q.get("expected_sources", [])
    if not expected_sources:
        return {"qid": q["id"], "dataset": q["dataset"], "skip": True}

    try:
        # Use internal retrieval method
        from quantumrag.core.generate.router import QueryRouter

        router = QueryRouter()
        classification = router.classify(q["query"])

        result = await engine._do_retrieval(q["query"], classification, TOP_K, None, True, None)

        retrieved_titles = (
            [s.document_title for s in result.sources] if hasattr(result, "sources") else []
        )

        # Also check chunk document_ids
        retrieved_doc_ids = [sc.chunk.document_id for sc in result.chunks] if result.chunks else []

        # Check recall: did we retrieve chunks from the expected source files?
        hits = 0
        for exp_src in expected_sources:
            found = any(exp_src in t for t in retrieved_titles) or any(
                exp_src in d for d in retrieved_doc_ids
            )
            if found:
                hits += 1

        recall = hits / len(expected_sources) if expected_sources else 0
        precision = hits / len(result.chunks) if result.chunks else 0

        return {
            "qid": q["id"],
            "dataset": q["dataset"],
            "difficulty": q.get("difficulty", "?"),
            "recall": round(recall, 4),
            "precision": round(precision, 4),
            "retrieved_count": len(result.chunks),
            "expected_sources": expected_sources,
            "top_score": round(result.chunks[0].score, 4) if result.chunks else 0,
        }

    except Exception as e:
        return {
            "qid": q["id"],
            "dataset": q["dataset"],
            "difficulty": q.get("difficulty", "?"),
            "recall": 0,
            "precision": 0,
            "error": str(e)[:100],
        }


async def run_all():
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def bounded(q):
        async with semaphore:
            return await test_retrieval(q)

    print(f"\n  Running retrieval test (concurrency={CONCURRENCY})...\n")
    t0 = time.perf_counter()
    results = await asyncio.gather(*(bounded(q) for q in all_questions))
    wall = time.perf_counter() - t0
    return list(results), wall


results, wall_time = asyncio.run(run_all())

# --- Analyze ---
tested = [r for r in results if not r.get("skip")]
total = len(tested)
recall_hits = sum(1 for r in tested if r.get("recall", 0) > 0)
avg_recall = sum(r.get("recall", 0) for r in tested) / total if total else 0
avg_top_score = sum(r.get("top_score", 0) for r in tested) / total if total else 0

# Per-dataset breakdown
ds_stats: dict[str, dict] = {}
for ds_path in datasets:
    ds_id = ds_path.name
    subset = [r for r in tested if r.get("dataset") == ds_id]
    if subset:
        ds_recall = sum(r.get("recall", 0) for r in subset) / len(subset)
        ds_hit = sum(1 for r in subset if r.get("recall", 0) > 0)
        ds_stats[ds_id] = {
            "total": len(subset),
            "hit": ds_hit,
            "recall": round(ds_recall, 4),
        }

# Per-difficulty
diff_stats: dict[str, dict] = {}
for diff in ["easy", "hard", "extreme"]:
    subset = [r for r in tested if r.get("difficulty") == diff]
    if subset:
        d_recall = sum(r.get("recall", 0) for r in subset) / len(subset)
        d_hit = sum(1 for r in subset if r.get("recall", 0) > 0)
        diff_stats[diff] = {"total": len(subset), "hit": d_hit, "recall": round(d_recall, 4)}

# --- Print ---
print(f"{'=' * 60}")
print(
    f"  RETRIEVAL RESULTS: {recall_hits}/{total} queries found correct source ({avg_recall * 100:.1f}% avg recall)"
)
print(f"  Avg top score: {avg_top_score:.4f} | Wall time: {wall_time:.1f}s")
print(f"{'=' * 60}")

print(f"\n  {'Dataset':<10} {'Hit/Total':>10} {'Recall':>10}")
print(f"  {'-' * 30}")
for ds_id, info in ds_stats.items():
    print(f"  {ds_id:<10} {info['hit']}/{info['total']:>7} {info['recall'] * 100:>9.0f}%")

print(f"\n  {'Difficulty':<10} {'Hit/Total':>10} {'Recall':>10}")
print(f"  {'-' * 30}")
for diff, info in diff_stats.items():
    print(f"  {diff:<10} {info['hit']}/{info['total']:>7} {info['recall'] * 100:>9.0f}%")

# Zero-recall questions (retrieval completely failed)
zero_recall = [r for r in tested if r.get("recall", 0) == 0]
if zero_recall:
    print(f"\n  Zero-recall queries ({len(zero_recall)}):")
    for r in zero_recall[:10]:
        q = next((q for q in all_questions if q["id"] == r["qid"]), {})
        print(f"    {r['qid']:12s} score={r.get('top_score', 0):.3f} | {q.get('query', '')[:50]}")
    if len(zero_recall) > 10:
        print(f"    ... and {len(zero_recall) - 10} more")

print(f"\n  Completed in {wall_time:.1f}s")
