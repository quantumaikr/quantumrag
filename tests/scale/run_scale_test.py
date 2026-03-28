"""Scale test runner — measures retrieval recall at scale using real QA data.

Uses all QA dataset sources as base, with confuser variants for volume.
Queries are the actual QA questions with known expected_keywords.

Usage:
    python tests/scale/run_scale_test.py --multiplier 10   # ~230 docs
    python tests/scale/run_scale_test.py --multiplier 50   # ~1,150 docs
    python tests/scale/run_scale_test.py --multiplier 200  # ~4,600 docs
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# Load .env
_env_path = _PROJECT_ROOT / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _get_memory_mb() -> float:
    try:
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
    except Exception:
        return 0.0


def _get_git_hash() -> str:
    import subprocess

    try:
        return (
            subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=str(_PROJECT_ROOT))
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


def run_scale_test(multiplier: int = 10, seed: int = 42) -> dict:
    from tests.scale.corpus_generator import generate_corpus

    corpus_dir = _PROJECT_ROOT / f".scale_test_x{multiplier}"
    data_dir = corpus_dir / ".rag_data"

    print(f"{'=' * 60}")
    print(f"  QuantumRAG Scale Test — x{multiplier} multiplier")
    print(f"{'=' * 60}\n")

    # ------------------------------------------------------------------
    # Step 1: Generate corpus from real QA datasets
    # ------------------------------------------------------------------
    print("[1/5] Generating corpus from ds-001~ds-NNN sources...")
    t0 = time.perf_counter()
    corpus_meta = generate_corpus(
        multiplier=multiplier,
        output_dir=str(corpus_dir),
        seed=seed,
    )
    gen_time = time.perf_counter() - t0
    print(
        f"  → {corpus_meta['original_sources']} originals + "
        f"{corpus_meta['confuser_variants']} confusers = "
        f"{corpus_meta['total_docs']} docs in {gen_time:.1f}s"
    )
    print(f"  → Datasets: {corpus_meta['datasets_used']}")
    print(f"  → Queries: {corpus_meta['total_queries']} ({corpus_meta['queries_by_difficulty']})")

    # ------------------------------------------------------------------
    # Step 2: Ingest (minimal mode)
    # ------------------------------------------------------------------
    print("\n[2/5] Ingesting corpus (minimal mode)...")
    mem_before = _get_memory_mb()
    t0 = time.perf_counter()

    from quantumrag.core.config import QuantumRAGConfig
    from quantumrag.core.engine import Engine

    config = QuantumRAGConfig.default(
        storage={"data_dir": str(data_dir)},
        ingest={"mode": "minimal"},
    )
    engine = Engine(config=config)
    result = engine.ingest(str(corpus_dir / "sources"), mode="minimal")
    ingest_time = time.perf_counter() - t0
    mem_after = _get_memory_mb()

    actual_chunks = result.chunks
    actual_docs = result.documents
    cps = actual_chunks / ingest_time if ingest_time > 0 else 0

    print(
        f"  → {actual_docs} docs, {actual_chunks} chunks in {ingest_time:.1f}s "
        f"({cps:.0f} chunks/sec)"
    )
    print(f"  → Memory: {mem_after:.0f}MB (Δ+{mem_after - mem_before:.0f}MB)")

    # ------------------------------------------------------------------
    # Step 3: Retrieval Recall
    # ------------------------------------------------------------------
    print("\n[3/5] Retrieval recall test...")

    # Warmup
    print("  ANN warmup...")
    t_w = time.perf_counter()
    try:
        engine.query("warmup", top_k=1)
    except Exception:
        pass
    warmup_s = time.perf_counter() - t_w
    print(f"  → {warmup_s:.1f}s")

    with open(corpus_dir / "queries.yaml") as f:
        queries = yaml.safe_load(f)["queries"]

    # Run queries
    results_by_diff = {}
    all_latencies = []
    total_pass = 0
    total_fail = 0
    failed_details = []

    for q in queries:
        diff = q["difficulty"]
        expect_insuf = q.get("expect_insufficient", False)
        keywords = q["expected_keywords"]
        match_mode = q.get("match_mode", "any")

        t_q = time.perf_counter()
        try:
            qr = engine.query(q["query"], top_k=10)
            latency = (time.perf_counter() - t_q) * 1000
            answer = qr.answer
            confidence = qr.confidence.value

            if expect_insuf:
                passed = confidence == "insufficient_evidence"
            elif match_mode == "all":
                passed = all(kw.lower() in answer.lower() for kw in keywords)
            else:
                passed = any(kw.lower() in answer.lower() for kw in keywords)

        except Exception as e:
            latency = (time.perf_counter() - t_q) * 1000
            passed = False
            answer = f"ERROR: {e}"
            confidence = "error"

        all_latencies.append(latency)

        if diff not in results_by_diff:
            results_by_diff[diff] = {"pass": 0, "fail": 0}
        if passed:
            results_by_diff[diff]["pass"] += 1
            total_pass += 1
        else:
            results_by_diff[diff]["fail"] += 1
            total_fail += 1
            failed_details.append(
                {
                    "dataset": q["dataset"],
                    "qid": q["qid"],
                    "difficulty": diff,
                    "query": q["query"][:60],
                    "expected": keywords[:3],
                }
            )

        status = "PASS" if passed else "FAIL"
        print(
            f"  {status} [{q['dataset']}/{q['qid']}] [{diff}] "
            f"{q['query'][:45]}... ({latency:.0f}ms)"
        )

    total = total_pass + total_fail
    pass_rate = total_pass / total if total > 0 else 0

    # ------------------------------------------------------------------
    # Step 4: Performance summary
    # ------------------------------------------------------------------
    print("\n[4/5] Performance profiling...")

    lat_sorted = sorted(all_latencies)
    n = len(lat_sorted)
    p50 = lat_sorted[n // 2] if n else 0
    p95 = lat_sorted[int(n * 0.95)] if n else 0
    p99 = lat_sorted[int(n * 0.99)] if n else 0
    avg_lat = sum(all_latencies) / n if n else 0

    mem_final = _get_memory_mb()
    disk_mb = (
        sum(f.stat().st_size for f in data_dir.rglob("*") if f.is_file()) / (1024 * 1024)
        if data_dir.exists()
        else 0
    )

    print(f"  Latency: p50={p50:.0f}ms, p95={p95:.0f}ms, p99={p99:.0f}ms")
    print(f"  Memory: {mem_final:.0f}MB | Disk: {disk_mb:.1f}MB")

    # ------------------------------------------------------------------
    # Step 5: Cost estimation
    # ------------------------------------------------------------------
    print("\n[5/5] Cost estimation...")

    embed_tokens = actual_chunks * 680 + len(queries) * 50
    embed_cost = embed_tokens * 0.02 / 1_000_000
    llm_input = len(queries) * 5000
    llm_output = len(queries) * 500
    llm_cost = (llm_input * 0.10 + llm_output * 0.40) / 1_000_000
    total_cost = embed_cost + llm_cost

    print(f"  Embedding: {embed_tokens:,} tokens → ${embed_cost:.4f}")
    print(f"  LLM:       ${llm_cost:.4f}")
    print(f"  Total:     ${total_cost:.4f} (≈{int(total_cost * 1350)}원)")

    # ------------------------------------------------------------------
    # Build report
    # ------------------------------------------------------------------
    diff_summary = {}
    for diff, counts in results_by_diff.items():
        t = counts["pass"] + counts["fail"]
        diff_summary[diff] = {
            "total": t,
            "passed": counts["pass"],
            "pass_rate": round(counts["pass"] / t, 4) if t else 0,
        }

    report = {
        "scale_test_report": {
            "timestamp": datetime.now().isoformat(),
            "engine_version": _get_git_hash(),
            "multiplier": multiplier,
            "seed": seed,
            "corpus": {
                "datasets_used": corpus_meta["datasets_used"],
                "original_sources": corpus_meta["original_sources"],
                "confuser_variants": corpus_meta["confuser_variants"],
                "total_docs": actual_docs,
                "total_chunks": actual_chunks,
            },
            "ingest": {
                "mode": "minimal",
                "time_s": round(ingest_time, 1),
                "chunks_per_sec": round(cps, 1),
            },
            "recall": {
                "total": total,
                "passed": total_pass,
                "failed": total_fail,
                "pass_rate": round(pass_rate, 4),
                "by_difficulty": diff_summary,
            },
            "failed_queries": failed_details,
            "performance": {
                "warmup_s": round(warmup_s, 1),
                "query_latency_ms": {
                    "p50": round(p50),
                    "p95": round(p95),
                    "p99": round(p99),
                    "avg": round(avg_lat),
                },
                "memory_mb": round(mem_final),
                "disk_mb": round(disk_mb, 1),
            },
            "cost": {
                "embedding_tokens": embed_tokens,
                "embedding_cost_usd": round(embed_cost, 4),
                "llm_cost_usd": round(llm_cost, 4),
                "total_cost_usd": round(total_cost, 4),
                "total_cost_krw": int(total_cost * 1350),
            },
        }
    }

    # Save report
    report_dir = _PROJECT_ROOT / "tests" / "scale" / "reports"
    report_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_file = report_dir / f"scale-x{multiplier}-{ts}.yaml"
    with open(report_file, "w") as f:
        yaml.dump(report, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # Cleanup
    if corpus_dir.exists():
        shutil.rmtree(corpus_dir)

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"  RESULTS — x{multiplier} ({actual_docs} docs, {actual_chunks} chunks)")
    print(f"{'=' * 60}")
    print(f"  Pass rate:  {pass_rate:.1%} ({total_pass}/{total})")
    for diff, s in sorted(diff_summary.items()):
        print(f"    {diff:10s}: {s['pass_rate']:.0%} ({s['passed']}/{s['total']})")
    print(f"  Latency p95: {p95:.0f}ms")
    print(f"  Cost:        ${total_cost:.4f} ({int(total_cost * 1350)}원)")
    print(f"  Report:      {report_file}")
    print(f"{'=' * 60}")

    if failed_details:
        print(f"\n  Failed queries ({len(failed_details)}):")
        for fd in failed_details[:10]:
            print(f"    [{fd['dataset']}/{fd['qid']}] {fd['query']}...")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QuantumRAG Scale Test")
    parser.add_argument(
        "--multiplier", type=int, default=10, help="Confuser variants per source (10/50/200)"
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    run_scale_test(multiplier=args.multiplier, seed=args.seed)
