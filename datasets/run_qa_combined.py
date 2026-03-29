"""Combined QA Runner — all datasets merged into one corpus.

Tests what individual dataset runs CANNOT test:
1. Retrieval precision under noise (23 sources, ~300 chunks, top_k=10 = 3%)
2. Cross-domain interference (Python docs vs semiconductor vs AI regulations)
3. Retrieval recall — did the engine find chunks from the correct source documents?
4. Degradation analysis — which questions break when buried in a larger corpus?

Usage:
    .venv/bin/python datasets/run_qa_combined.py
"""

import asyncio
import hashlib
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Fix: project's datasets/ directory shadows the HuggingFace 'datasets' package
# that LanceDB depends on. Pre-import the real package before any lancedb import.
_project_root = str(Path(__file__).resolve().parent.parent)
_script_dir = str(Path(__file__).resolve().parent)
# Temporarily remove script dir from path, import real 'datasets', restore
if _script_dir in sys.path:
    sys.path.remove(_script_dir)
try:
    import datasets as _hf_datasets  # noqa: F401 — cache the real package
except ImportError:
    pass
sys.path.insert(0, _script_dir)

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

# --- Config ---
QUERY_TIMEOUT = 120  # Extended for full-mode queries
CONCURRENCY = 3  # Reduce to avoid Gemini rate limits
INGEST_MODE = "full"  # Full Triple Index (Original + HyPE + BM25)
SAMPLE_PER_DATASET = 0  # Full 105q baseline
NOISE_DOCS = 50  # Noise docs for scale testing. Uses local embeddings, no API cost.

# --- Collect all datasets ---
ds_root = Path(__file__).resolve().parent
combined_dir = ds_root / ".combined"
sources_dir = combined_dir / "sources"
data_dir = combined_dir / ".rag_data"
hash_file = combined_dir / ".sources_hash"

datasets = sorted(ds_root.glob("ds-*"))
if not datasets:
    print("  ERROR: No datasets found")
    sys.exit(1)

# Build source mapping: copy all sources with unique prefix
# ds-001/sources/001.md → .combined/sources/ds-001_001.md
source_map: dict[str, str] = {}  # "ds-001_001" → original path
all_questions: list[dict] = []

sources_dir.mkdir(parents=True, exist_ok=True)

for ds_path in datasets:
    ds_id = ds_path.name
    manifest_path = ds_path / "manifest.yaml"
    qa_path = ds_path / "qa.yaml"
    if not qa_path.exists():
        continue

    with open(qa_path) as f:
        qa = yaml.safe_load(f)

    # Copy sources with prefix
    src_dir = ds_path / "sources"
    if src_dir.exists():
        for src_file in sorted(src_dir.glob("*.md")):
            prefixed_name = f"{ds_id}_{src_file.name}"
            dest = sources_dir / prefixed_name
            shutil.copy2(src_file, dest)
            source_map[f"{ds_id}_{src_file.stem}"] = str(src_file)

    # Remap questions with dataset prefix
    ds_questions: list[dict] = []
    for q in qa.get("questions", []):
        remapped = dict(q)
        remapped["dataset"] = ds_id
        remapped["original_id"] = q["id"]
        remapped["id"] = f"{ds_id}:{q['id']}"
        remapped["expected_sources"] = [f"{ds_id}_{sid}" for sid in q.get("source_ids", [])]
        ds_questions.append(remapped)

    # Sample for speed: pick diverse difficulty mix per dataset
    if SAMPLE_PER_DATASET > 0 and len(ds_questions) > SAMPLE_PER_DATASET:
        sampled: list[dict] = []
        for diff in ["easy", "hard", "extreme"]:
            diff_qs = [q for q in ds_questions if q.get("difficulty") == diff]
            n = max(1, SAMPLE_PER_DATASET * len(diff_qs) // len(ds_questions))
            sampled.extend(diff_qs[:n])
        # Fill remaining slots
        remaining = [q for q in ds_questions if q not in sampled]
        sampled.extend(remaining[: SAMPLE_PER_DATASET - len(sampled)])
        all_questions.extend(sampled[:SAMPLE_PER_DATASET])
    else:
        all_questions.extend(ds_questions)

# Add noise documents for scale testing
if NOISE_DOCS > 0:
    # Import noise generator from same directory (not HuggingFace datasets package)
    import importlib.util

    _ng_spec = importlib.util.spec_from_file_location(
        "noise_generator", str(ds_root / "noise_generator.py")
    )
    _ng_mod = importlib.util.module_from_spec(_ng_spec)  # type: ignore[arg-type]
    _ng_spec.loader.exec_module(_ng_mod)  # type: ignore[union-attr]
    generate_noise_docs = _ng_mod.generate_noise_docs

    noise_dir = combined_dir / "noise"
    n_generated = generate_noise_docs(noise_dir, NOISE_DOCS)
    for noise_file in sorted(noise_dir.glob("*.md")):
        dest = sources_dir / noise_file.name
        shutil.copy2(noise_file, dest)
    noise_count = len(list(noise_dir.glob("*.md")))
else:
    noise_count = 0

total_sources = len(source_map) + noise_count

print("=" * 70)
print("  Combined QA Run — All Datasets Merged + Noise")
print("=" * 70)
print(f"\n  Datasets: {len(datasets)} ({', '.join(d.name for d in datasets)})")
print(f"  Sources:  {len(source_map)} real + {noise_count} noise = {total_sources} total")
print(
    f"  Questions: {len(all_questions)} (sampled {SAMPLE_PER_DATASET}/dataset)"
    if SAMPLE_PER_DATASET > 0
    else f"  Questions: {len(all_questions)}"
)


# --- Ingest with caching ---
def compute_sources_hash() -> str:
    h = hashlib.sha256()
    for f in sorted(sources_dir.glob("*")):
        if f.is_file():
            h.update(f.name.encode())
            h.update(f.read_bytes())
    return h.hexdigest()[:16]


current_hash = compute_sources_hash()
cached_hash = hash_file.read_text().strip() if hash_file.exists() else ""

# Use local embeddings for scale testing (no API cost, no rate limits)
config = QuantumRAGConfig.default(storage={"data_dir": str(data_dir)})
config.models.embedding.provider = "local"
config.models.embedding.model = "BAAI/bge-m3"
config.models.embedding.dimensions = 1024
engine = Engine(config=config)

if current_hash == cached_hash and data_dir.exists():
    print(f"\n  Ingest: cached (hash={current_hash})")
    engine.ingest(str(sources_dir))
    ingest_docs, ingest_chunks, ingest_elapsed = 0, 0, 0.0
else:
    if data_dir.exists():
        shutil.rmtree(data_dir)
    print(f"\n  Ingesting {len(source_map)} combined sources (mode={INGEST_MODE})...")
    t_ingest = time.perf_counter()
    ingest_result = engine.ingest(str(sources_dir), mode=INGEST_MODE)
    ingest_elapsed = time.perf_counter() - t_ingest
    ingest_docs = ingest_result.documents
    ingest_chunks = ingest_result.chunks
    print(f"  Documents: {ingest_docs} | Chunks: {ingest_chunks} | Time: {ingest_elapsed:.1f}s")
    hash_file.write_text(current_hash)


# --- Query with retrieval tracking ---
async def run_query(q: dict) -> dict:
    t0 = time.perf_counter()
    try:
        qr = await asyncio.wait_for(
            engine.aquery(q["query"]),
            timeout=QUERY_TIMEOUT,
        )
        elapsed = time.perf_counter() - t0

        answer = qr.answer
        confidence = qr.confidence.value
        sources_count = len(qr.sources)

        # Answer scoring (same as individual runner)
        keywords = q.get("expected_keywords", [])
        match_mode = q.get("match_mode", "any")
        expect_insufficient = q.get("expect_insufficient", False)

        if expect_insufficient:
            passed = confidence == "insufficient_evidence" or any(
                kw.lower() in answer.lower() for kw in keywords
            )
        elif match_mode == "all":
            passed = all(kw.lower() in answer.lower() for kw in keywords)
        else:
            passed = any(kw.lower() in answer.lower() for kw in keywords)

        # Retrieval quality: check if retrieved sources match expected source documents
        expected_sources = q.get("expected_sources", [])

        # Collect all identifiers from retrieved results for matching
        retrieved_ids: set[str] = set()
        for s in qr.sources:
            retrieved_ids.add(s.document_title.lower())
            retrieved_ids.add(s.chunk_id.lower())
        # Also check answer text for source file references
        answer_lower = answer.lower()

        retrieval_hits = []
        for exp_src in expected_sources:
            # exp_src is like "ds-001_001", source file is "ds-001_001.md"
            # Check multiple matching strategies:
            hit = (
                any(exp_src.lower() in rid for rid in retrieved_ids)
                or exp_src.lower() in answer_lower
            )
            retrieval_hits.append({"expected": exp_src, "found": hit})

        retrieval_recall = (
            sum(1 for h in retrieval_hits if h["found"]) / len(retrieval_hits)
            if retrieval_hits
            else 1.0
        )

        # Noise ratio: simplified — based on answer pass/fail + recall
        noise_ratio = 1.0 - retrieval_recall if not passed else 0.0

        status = "\033[92mPASS\033[0m" if passed else "\033[91mFAIL\033[0m"
        recall_str = f"R={retrieval_recall:.0%}" if expected_sources else "R=n/a"
        print(
            f"  {status} {q['id']:12s} [{q.get('difficulty', '?'):7s}] {elapsed:5.1f}s {recall_str} | {q['query'][:45]}"
        )

        return {
            "qid": q["id"],
            "dataset": q["dataset"],
            "query": q["query"],
            "difficulty": q.get("difficulty", "medium"),
            "type": q.get("type", "factual"),
            "answer": answer[:300],
            "confidence": confidence,
            "sources_count": sources_count,
            "latency_s": round(elapsed, 2),
            "passed": passed,
            "retrieval_recall": round(retrieval_recall, 4),
            "noise_ratio": round(noise_ratio, 4),
            "expected_keywords": keywords,
            "matched_keywords": [kw for kw in keywords if kw.lower() in answer.lower()],
        }

    except asyncio.TimeoutError:
        elapsed = time.perf_counter() - t0
        print(
            f"  \033[93mTIMEOUT\033[0m {q['id']:12s} [{q.get('difficulty', '?'):7s}] {elapsed:5.1f}s        | {q['query'][:45]}"
        )
        return {
            "qid": q["id"],
            "dataset": q["dataset"],
            "query": q["query"],
            "difficulty": q.get("difficulty", "medium"),
            "type": q.get("type", "factual"),
            "answer": "",
            "confidence": "timeout",
            "sources_count": 0,
            "latency_s": round(elapsed, 2),
            "passed": False,
            "retrieval_recall": 0.0,
            "noise_ratio": 1.0,
            "error": f"Timeout after {QUERY_TIMEOUT}s",
        }

    except Exception as e:
        elapsed = time.perf_counter() - t0
        print(f"  \033[91mERROR\033[0m {q['id']:12s}: {e}")
        return {
            "qid": q["id"],
            "dataset": q["dataset"],
            "query": q["query"],
            "difficulty": q.get("difficulty", "medium"),
            "type": q.get("type", "factual"),
            "answer": "",
            "confidence": "error",
            "sources_count": 0,
            "latency_s": round(elapsed, 2),
            "passed": False,
            "retrieval_recall": 0.0,
            "noise_ratio": 1.0,
            "error": str(e),
        }


async def run_all():
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def bounded(q):
        async with semaphore:
            return await run_query(q)

    print(
        f"\n  Running {len(all_questions)} questions (concurrency={CONCURRENCY}, timeout={QUERY_TIMEOUT}s)...\n"
    )
    t_total = time.perf_counter()
    results = await asyncio.gather(*(bounded(q) for q in all_questions))
    wall_time = time.perf_counter() - t_total
    return list(results), wall_time


# --- Main ---
results, wall_time = asyncio.run(run_all())

# --- Compute metrics ---
total = len(results)
passed_count = sum(1 for r in results if r["passed"])
timeout_count = sum(1 for r in results if r.get("error", "").startswith("Timeout"))
pass_rate = passed_count / total if total > 0 else 0
avg_recall = sum(r.get("retrieval_recall", 0) for r in results) / total if total > 0 else 0
avg_noise = sum(r.get("noise_ratio", 0) for r in results) / total if total > 0 else 0

# Git hash
try:
    git_hash = (
        subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=str(ds_root.parent))
        .decode()
        .strip()
    )
except Exception:
    git_hash = "unknown"

# --- Load individual run results for comparison ---
individual_rates: dict[str, float] = {}
for ds_path in datasets:
    ds_id = ds_path.name
    run_files = sorted((ds_path / "runs").glob("run-*.yaml"))
    if run_files:
        with open(run_files[-1]) as f:
            rd = yaml.safe_load(f)
        individual_rates[ds_id] = rd.get("summary", {}).get("pass_rate", 0)

# --- Per-dataset breakdown in combined mode ---
ds_breakdown: dict[str, dict] = {}
for ds_path in datasets:
    ds_id = ds_path.name
    subset = [r for r in results if r.get("dataset") == ds_id]
    if subset:
        sp = sum(1 for r in subset if r["passed"])
        sr = sum(r.get("retrieval_recall", 0) for r in subset) / len(subset)
        ds_breakdown[ds_id] = {
            "total": len(subset),
            "passed": sp,
            "pass_rate": round(sp / len(subset), 4),
            "individual_rate": individual_rates.get(ds_id, 0),
            "degradation": round(individual_rates.get(ds_id, 0) - sp / len(subset), 4),
            "avg_retrieval_recall": round(sr, 4),
        }

# --- Save results ---
runs_dir = combined_dir / "runs"
runs_dir.mkdir(parents=True, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
run_file = runs_dir / f"combined-{git_hash}-{timestamp}.yaml"

run_data = {
    "engine_version": git_hash,
    "timestamp": datetime.now().isoformat(),
    "mode": "combined",
    "corpus": {
        "datasets": [d.name for d in datasets],
        "total_sources": len(source_map),
        "total_chunks": ingest_chunks,
        "total_questions": total,
    },
    "execution": {
        "concurrency": CONCURRENCY,
        "query_timeout_s": QUERY_TIMEOUT,
        "wall_time_s": round(wall_time, 2),
        "sum_latency_s": round(sum(r["latency_s"] for r in results), 2),
    },
    "results": results,
    "summary": {
        "total": total,
        "passed": passed_count,
        "failed": total - passed_count,
        "timeout": timeout_count,
        "pass_rate": round(pass_rate, 4),
        "avg_latency_s": round(sum(r["latency_s"] for r in results) / total, 2) if total > 0 else 0,
        "avg_retrieval_recall": round(avg_recall, 4),
        "avg_noise_ratio": round(avg_noise, 4),
        "wall_time_s": round(wall_time, 2),
        "by_dataset": ds_breakdown,
        "by_difficulty": {},
        "by_type": {},
    },
}

# Breakdown by difficulty
for diff in ["easy", "hard", "extreme"]:
    subset = [r for r in results if r.get("difficulty") == diff]
    if subset:
        sp = sum(1 for r in subset if r["passed"])
        sr = sum(r.get("retrieval_recall", 0) for r in subset) / len(subset)
        run_data["summary"]["by_difficulty"][diff] = {
            "total": len(subset),
            "passed": sp,
            "pass_rate": round(sp / len(subset), 4),
            "avg_retrieval_recall": round(sr, 4),
        }

# Breakdown by type
for t in sorted(set(r.get("type", "unknown") for r in results)):
    subset = [r for r in results if r.get("type") == t]
    if subset:
        sp = sum(1 for r in subset if r["passed"])
        sr = sum(r.get("retrieval_recall", 0) for r in subset) / len(subset)
        run_data["summary"]["by_type"][t] = {
            "total": len(subset),
            "passed": sp,
            "pass_rate": round(sp / len(subset), 4),
            "avg_retrieval_recall": round(sr, 4),
        }

with open(run_file, "w") as f:
    yaml.dump(run_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

# --- Print report ---
print(f"\n{'=' * 70}")
print(f"  COMBINED RESULTS: {passed_count}/{total} ({pass_rate * 100:.1f}%)")
if timeout_count:
    print(f"  TIMEOUT: {timeout_count} queries exceeded {QUERY_TIMEOUT}s")
print(f"  Retrieval Recall: {avg_recall * 100:.1f}%  |  Noise Ratio: {avg_noise * 100:.1f}%")
print(f"{'=' * 70}")

# Degradation analysis
print(f"\n  {'Dataset':<10} {'Individual':>10} {'Combined':>10} {'Δ Degrade':>10} {'Recall':>10}")
print(f"  {'-' * 50}")
for ds_id, info in ds_breakdown.items():
    ind_str = f"{info['individual_rate'] * 100:.0f}%"
    com_str = f"{info['pass_rate'] * 100:.0f}%"
    deg = info["degradation"]
    deg_str = f"{deg * 100:+.0f}%" if deg != 0 else "0%"
    rec_str = f"{info['avg_retrieval_recall'] * 100:.0f}%"
    print(f"  {ds_id:<10} {ind_str:>10} {com_str:>10} {deg_str:>10} {rec_str:>10}")

print(f"\n  By difficulty:")
for diff in ["easy", "hard", "extreme"]:
    bd = run_data["summary"]["by_difficulty"].get(diff)
    if bd:
        print(
            f"  {diff:8s}: {bd['passed']}/{bd['total']} ({bd['pass_rate'] * 100:.0f}%)  recall={bd['avg_retrieval_recall'] * 100:.0f}%"
        )

# Identify retrieval-caused failures
retrieval_failures = [
    r
    for r in results
    if not r["passed"] and r.get("retrieval_recall", 1) < 0.5 and not r.get("error")
]
generation_failures = [
    r
    for r in results
    if not r["passed"] and r.get("retrieval_recall", 0) >= 0.5 and not r.get("error")
]

print(f"\n  Failure diagnosis:")
print(f"    Retrieval failures (recall < 50%): {len(retrieval_failures)}")
print(f"    Generation failures (recall >= 50%): {len(generation_failures)}")
print(f"    Timeout failures: {timeout_count}")

if retrieval_failures:
    print(f"\n  Top retrieval failures:")
    for r in sorted(retrieval_failures, key=lambda x: x["retrieval_recall"])[:5]:
        print(
            f"    {r['qid']:12s} recall={r['retrieval_recall'] * 100:.0f}% noise={r['noise_ratio'] * 100:.0f}% | {r['query'][:50]}"
        )

sum_latency = sum(r["latency_s"] for r in results)
print(f"\n  Wall time:   {wall_time:.1f}s (parallelism saved {sum_latency - wall_time:.0f}s)")
print(f"  Avg latency: {run_data['summary']['avg_latency_s']}s")
print(f"  Saved: {run_file}")
