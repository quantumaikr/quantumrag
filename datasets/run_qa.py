"""QA Dataset Runner — shared runner for all datasets.

Usage:
    .venv/bin/python datasets/run_qa.py ds-001
    .venv/bin/python datasets/run_qa.py ds-003

Optimizations over the original per-dataset runners:
1. Ingest caching: skip re-ingest if sources unchanged (hash check)
2. Per-query timeout: 120s limit prevents slow queries from blocking
3. Parallel execution: 3 concurrent queries (respects API rate limits)
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

import yaml

# --- Args ---
if len(sys.argv) < 2:
    # Auto-detect most recent dataset
    ds_root = Path(__file__).resolve().parent
    candidates = sorted(ds_root.glob("ds-*"), reverse=True)
    if not candidates:
        print("Usage: python datasets/run_qa.py <ds-id>")
        sys.exit(1)
    ds_dir = candidates[0]
    ds_id = ds_dir.name
    print(f"  Auto-selected: {ds_id}")
else:
    ds_id = sys.argv[1]
    ds_dir = Path(__file__).resolve().parent / ds_id

if not ds_dir.exists():
    print(f"  ERROR: {ds_dir} does not exist")
    sys.exit(1)

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
QUERY_TIMEOUT = 120  # seconds per query
CONCURRENCY = 3  # parallel queries

# --- Setup ---
sources_dir = ds_dir / "sources"
data_dir = ds_dir / ".rag_data"
hash_file = ds_dir / ".sources_hash"

with open(ds_dir / "qa.yaml") as f:
    qa = yaml.safe_load(f)

print("=" * 60)
print(f"  QA Dataset Run: {ds_id}")
print("=" * 60)


# --- Ingest with caching ---
def compute_sources_hash() -> str:
    """Hash all source files to detect changes."""
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

if current_hash == cached_hash and data_dir.exists():
    print(f"\n  Ingest: cached (hash={current_hash})")
    engine.ingest(str(sources_dir))
    ingest_docs, ingest_chunks, ingest_elapsed = 0, 0, 0.0
else:
    if data_dir.exists():
        shutil.rmtree(data_dir)
    print(f"\n  Ingesting from {sources_dir}...")
    t_ingest = time.perf_counter()
    ingest_result = engine.ingest(str(sources_dir))
    ingest_elapsed = time.perf_counter() - t_ingest
    ingest_docs = ingest_result.documents
    ingest_chunks = ingest_result.chunks
    print(f"  Documents: {ingest_docs} | Chunks: {ingest_chunks} | Time: {ingest_elapsed:.1f}s")
    hash_file.write_text(current_hash)

    if ingest_docs == 0 and not data_dir.exists():
        print("  ERROR: No documents ingested — aborting")
        sys.exit(1)


# --- Query execution with timeout ---
async def run_query(q: dict) -> dict:
    """Run a single query with timeout."""
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

        matched = [kw for kw in keywords if kw.lower() in answer.lower()]
        status = "\033[92mPASS\033[0m" if passed else "\033[91mFAIL\033[0m"
        print(
            f"  {status} {q['id']} [{q.get('difficulty','?'):7s}] {elapsed:5.1f}s | {q['query'][:50]}"
        )
        if not passed:
            print(f"         expected: {keywords}")
            print(f"         matched:  {matched}")

        return {
            "qid": q["id"],
            "query": q["query"],
            "difficulty": q.get("difficulty", "medium"),
            "type": q.get("type", "factual"),
            "answer": answer[:500],
            "confidence": confidence,
            "sources_count": sources_count,
            "latency_s": round(elapsed, 2),
            "passed": passed,
            "expected_keywords": keywords,
            "matched_keywords": matched,
        }

    except asyncio.TimeoutError:
        elapsed = time.perf_counter() - t0
        print(
            f"  \033[93mTIMEOUT\033[0m {q['id']} [{q.get('difficulty','?'):7s}] {elapsed:5.1f}s | {q['query'][:50]}"
        )
        return {
            "qid": q["id"],
            "query": q["query"],
            "difficulty": q.get("difficulty", "medium"),
            "type": q.get("type", "factual"),
            "answer": "",
            "confidence": "timeout",
            "sources_count": 0,
            "latency_s": round(elapsed, 2),
            "passed": False,
            "error": f"Timeout after {QUERY_TIMEOUT}s",
        }

    except Exception as e:
        elapsed = time.perf_counter() - t0
        print(f"  \033[91mERROR\033[0m {q['id']}: {e}")
        return {
            "qid": q["id"],
            "query": q["query"],
            "difficulty": q.get("difficulty", "medium"),
            "type": q.get("type", "factual"),
            "answer": "",
            "confidence": "error",
            "sources_count": 0,
            "latency_s": round(elapsed, 2),
            "passed": False,
            "error": str(e),
        }


async def run_all():
    """Run all queries with bounded concurrency."""
    semaphore = asyncio.Semaphore(CONCURRENCY)
    questions = qa["questions"]

    async def bounded(q):
        async with semaphore:
            return await run_query(q)

    print(
        f"\n  Running {len(questions)} questions (concurrency={CONCURRENCY}, timeout={QUERY_TIMEOUT}s)...\n"
    )
    t_total = time.perf_counter()
    results = await asyncio.gather(*(bounded(q) for q in questions))
    wall_time = time.perf_counter() - t_total
    return list(results), wall_time


# --- Main ---
results, wall_time = asyncio.run(run_all())

# Summary
total = len(results)
passed_count = sum(1 for r in results if r["passed"])
timeout_count = sum(1 for r in results if r.get("error", "").startswith("Timeout"))
pass_rate = passed_count / total if total > 0 else 0

# Git hash
try:
    git_hash = (
        subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(ds_dir.parent.parent),
        )
        .decode()
        .strip()
    )
except Exception:
    git_hash = "unknown"

# Save run
runs_dir = ds_dir / "runs"
runs_dir.mkdir(exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
run_file = runs_dir / f"run-{git_hash}-{timestamp}.yaml"

run_data = {
    "engine_version": git_hash,
    "timestamp": datetime.now().isoformat(),
    "dataset": ds_id,
    "ingest": {
        "documents": ingest_docs,
        "chunks": ingest_chunks,
        "elapsed_s": round(ingest_elapsed, 2),
        "cached": current_hash == cached_hash,
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
        "wall_time_s": round(wall_time, 2),
        "by_difficulty": {},
        "by_type": {},
    },
}

# Breakdown by difficulty
for diff in ["easy", "hard", "extreme"]:
    subset = [r for r in results if r.get("difficulty") == diff]
    if subset:
        sp = sum(1 for r in subset if r["passed"])
        run_data["summary"]["by_difficulty"][diff] = {
            "total": len(subset),
            "passed": sp,
            "pass_rate": round(sp / len(subset), 4),
        }

# Breakdown by type
for t in sorted(set(r.get("type", "unknown") for r in results)):
    subset = [r for r in results if r.get("type") == t]
    if subset:
        sp = sum(1 for r in subset if r["passed"])
        run_data["summary"]["by_type"][t] = {
            "total": len(subset),
            "passed": sp,
            "pass_rate": round(sp / len(subset), 4),
        }

with open(run_file, "w") as f:
    yaml.dump(run_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

# Print summary
print(f"\n{'=' * 60}")
print(f"  RESULTS: {passed_count}/{total} ({pass_rate*100:.1f}%)")
if timeout_count:
    print(f"  TIMEOUT: {timeout_count} queries exceeded {QUERY_TIMEOUT}s")
print(f"{'=' * 60}")

for diff in ["easy", "hard", "extreme"]:
    bd = run_data["summary"]["by_difficulty"].get(diff)
    if bd:
        print(f"  {diff:8s}: {bd['passed']}/{bd['total']} ({bd['pass_rate']*100:.0f}%)")

sum_latency = sum(r["latency_s"] for r in results)
print(f"\n  Wall time:   {wall_time:.1f}s (parallelism saved {sum_latency - wall_time:.0f}s)")
print(f"  Sum latency: {sum_latency:.1f}s")
print(f"  Avg latency: {run_data['summary']['avg_latency_s']}s")
print(f"  Saved: {run_file}")


# --- Graduation check ---
def check_graduation():
    """Check if dataset meets graduation criteria and update manifest."""
    manifest_path = ds_dir / "manifest.yaml"
    with open(manifest_path) as f:
        manifest = yaml.safe_load(f)

    if manifest.get("status") == "graduated":
        print(f"\n  Already graduated.")
        return

    threshold = manifest.get("graduation_threshold", {})
    min_rate = threshold.get("pass_rate", 0.85)
    min_runs = threshold.get("min_runs", 3)

    # Count qualifying runs (pass_rate >= threshold)
    run_files = sorted((ds_dir / "runs").glob("run-*.yaml"))
    qualifying = 0
    for rf in run_files:
        with open(rf) as f:
            rd = yaml.safe_load(f)
        if rd.get("summary", {}).get("pass_rate", 0) >= min_rate:
            qualifying += 1

    print(f"\n  Graduation: {qualifying}/{min_runs} qualifying runs (>= {min_rate*100:.0f}%)")

    if qualifying >= min_runs:
        manifest["status"] = "graduated"
        manifest["graduated_date"] = datetime.now().strftime("%Y-%m-%d")
        with open(manifest_path, "w") as f:
            yaml.dump(manifest, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        print(f"  \033[92m>>> GRADUATED! status updated in manifest.yaml\033[0m")

        # Clean up .rag_data to save disk
        if data_dir.exists():
            shutil.rmtree(data_dir)
            print(f"  Cleaned up: {data_dir}")
        if hash_file.exists():
            hash_file.unlink()
    else:
        remaining = min_runs - qualifying
        print(f"  {remaining} more qualifying run(s) needed")


check_graduation()


# --- Update STATUS.md ---
def update_status():
    """Generate datasets/STATUS.md with all datasets summary."""
    ds_root = Path(__file__).resolve().parent
    status_lines = [
        "# QA Datasets Status",
        f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "| Dataset | Name | Status | Runs | Best | Latest | Threshold | Questions |",
        "|---------|------|--------|------|------|--------|-----------|-----------|",
    ]

    for ds_path in sorted(ds_root.glob("ds-*")):
        manifest_path = ds_path / "manifest.yaml"
        if not manifest_path.exists():
            continue
        with open(manifest_path) as f:
            m = yaml.safe_load(f)

        ds_name = m.get("name", ds_path.name)[:30]
        status = m.get("status", "unknown")
        threshold = m.get("graduation_threshold", {}).get("pass_rate", 0)
        min_runs = m.get("graduation_threshold", {}).get("min_runs", 3)

        # Load qa for question count
        qa_path = ds_path / "qa.yaml"
        q_count = 0
        if qa_path.exists():
            with open(qa_path) as f:
                q_data = yaml.safe_load(f)
            q_count = len(q_data.get("questions", []))

        # Load runs
        run_files = sorted((ds_path / "runs").glob("run-*.yaml"))
        n_runs = len(run_files)
        best_rate = 0.0
        latest_rate = 0.0
        for rf in run_files:
            with open(rf) as f:
                rd = yaml.safe_load(f)
            rate = rd.get("summary", {}).get("pass_rate", 0)
            best_rate = max(best_rate, rate)
            latest_rate = rate

        status_icon = {"graduated": "graduated", "active": "active"}.get(status, status)
        best_str = f"{best_rate*100:.0f}%" if n_runs > 0 else "-"
        latest_str = f"{latest_rate*100:.0f}%" if n_runs > 0 else "-"

        status_lines.append(
            f"| {ds_path.name} | {ds_name} | {status_icon} | {n_runs}/{min_runs} | {best_str} | {latest_str} | {threshold*100:.0f}% | {q_count} |"
        )

    # Failure patterns across datasets
    status_lines.extend(["", "## Recent Failures", ""])
    for ds_path in sorted(ds_root.glob("ds-*")):
        run_files = sorted((ds_path / "runs").glob("run-*.yaml"))
        if not run_files:
            continue
        with open(run_files[-1]) as f:
            rd = yaml.safe_load(f)
        failures = [r for r in rd.get("results", []) if not r.get("passed")]
        if not failures:
            continue
        status_lines.append(f"**{ds_path.name}** (latest: {rd['summary']['pass_rate']*100:.0f}%)")
        for fail in failures:
            err = fail.get("error", "keyword mismatch")
            status_lines.append(
                f"- {fail['qid']} [{fail.get('difficulty','')}] {fail['query'][:50]}... → {err}"
            )
        status_lines.append("")

    (ds_root / "STATUS.md").write_text("\n".join(status_lines) + "\n")
    print(f"\n  Updated: datasets/STATUS.md")


update_status()
