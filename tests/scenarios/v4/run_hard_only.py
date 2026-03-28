"""QuantumRAG Focused Test — Hard/Extreme only.

Runs only hard and extreme difficulty test cases for fast iteration.
Shares test cases from test_cases.py.

Usage:
    uv run python tests/scenarios/v4/run_hard_only.py
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

# Load .env
env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

import sys

from quantumrag.core.config import QuantumRAGConfig
from quantumrag.core.engine import Engine

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_cases import (
    DIVIDER,
    DOCS_DIR,
    FAIL,
    PASS,
    PROJECT_ROOT,
    # All test case lists
    S1_FACTUAL,
    S2_MULTIHOP,
    S3_NUMERICAL,
    S4_TEMPORAL,
    S5_NEGATION,
    S6_CROSS_DOC,
    S7_PARAPHRASE,
    S9_EDGE,
    S10_PRECISION,
    S11_IMPLICIT,
    S12_COMPETITIVE,
    S13_CONDITIONAL,
    S14_FILTER,
    S15_DERIVED,
    S16_CROSSCHECK,
    S17_FORMATS,
    S18_INCOMPLETE,
    S19_CONTRADICTION,
    S20_MIXED_LANG,
    S21_COUNTERFACTUAL,
    S22_PRECISION_CROSS,
    S23_COMPLEX_COND,
    S24_ABSTRACT,
    S25_REVERSE,
    S26_TABLE,
    S27_COMPLETENESS,
    S28_BOUNDARY,
    S29_PDF_DEEP,
    S30_AGGREGATION,
    S31_RERANKER,
    S32_HWPX_DEEP,
    S33_CROSS_NUM,
    SUB_DIVIDER,
    ScenarioReport,
    TestCase,
    generate_report,
    print_result,
    run_multiturn,
    run_test,
)

DATA_DIR = PROJECT_ROOT / "test_scenario_data"


def filter_hard(cases: list[TestCase]) -> list[TestCase]:
    """Filter to only hard and extreme difficulty cases."""
    return [tc for tc in cases if tc.difficulty in ("hard", "extreme")]


def main() -> None:
    print(DIVIDER)
    print("  QuantumRAG -- FOCUSED Test (Hard/Extreme only)")
    print(DIVIDER)

    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)

    config = QuantumRAGConfig.default(storage={"data_dir": str(DATA_DIR)})
    engine = Engine(config=config)

    print(
        f"\n  Config: top_k={config.retrieval.top_k}, "
        f"multiplier={config.retrieval.fusion_candidate_multiplier}, "
        f"max_context={config.generation.max_context_chars}"
    )
    print(f"  Reranker: {config.models.reranker.provider}")

    # Ingest
    print(f"\n  Ingesting from {DOCS_DIR}...")
    t0 = time.perf_counter()
    result = engine.ingest(DOCS_DIR)
    elapsed = time.perf_counter() - t0
    ingest_info = {"documents": result.documents, "chunks": result.chunks, "elapsed": elapsed}
    print(f"  Documents: {result.documents} | Chunks: {result.chunks} | Time: {elapsed:.1f}s")

    if result.documents == 0:
        print(f"  {FAIL} No documents -- aborting")
        return

    # Define all scenario groups with their cases
    all_groups = [
        ("S1: 사실 확인", S1_FACTUAL),
        ("S2: 멀티홉 추론", S2_MULTIHOP),
        ("S3: 수치 계산/비교", S3_NUMERICAL),
        ("S4: 시간/버전 추론", S4_TEMPORAL),
        ("S5: 부정형/제외", S5_NEGATION),
        ("S6: 교차 문서 종합", S6_CROSS_DOC),
        ("S7: 패러프레이즈", S7_PARAPHRASE),
        # S8 handled separately (multi-turn)
        ("S9: 엣지 케이스", S9_EDGE),
        ("S10: 정밀 검색", S10_PRECISION),
        ("S11: 암묵적 추론", S11_IMPLICIT),
        ("S12: 경쟁사 비교", S12_COMPETITIVE),
        ("S13: 조건부 추론", S13_CONDITIONAL),
        ("S14: 다중 제약 필터링", S14_FILTER),
        ("S15: 정량적 파생 계산", S15_DERIVED),
        ("S16: 교차 검증", S16_CROSSCHECK),
        ("S17: 문서 포맷 (PDF/HWPX)", S17_FORMATS),
        ("S18: 불완전 정보 추론", S18_INCOMPLETE),
        ("S19: 모순/불일치 감지", S19_CONTRADICTION),
        ("S20: 한영 혼합 질의", S20_MIXED_LANG),
        ("S21: 반사실적 추론", S21_COUNTERFACTUAL),
        ("S22: 수치 교차 검증", S22_PRECISION_CROSS),
        ("S23: 복합 조건부 질의", S23_COMPLEX_COND),
        ("S24: 추상적/메타 질의", S24_ABSTRACT),
        ("S25: 역방향 추론", S25_REVERSE),
        ("S26: 테이블 구조 이해", S26_TABLE),
        ("S27: 답변 완전성", S27_COMPLETENESS),
        ("S28: 청크 경계 강건성", S28_BOUNDARY),
        ("S29: PDF 심층 구조 추출", S29_PDF_DEEP),
        ("S30: 산재 정보 종합 수집", S30_AGGREGATION),
        ("S31: Reranker 강화 검색", S31_RERANKER),
        ("S32: HWPX 심층 추출", S32_HWPX_DEEP),
        ("S33: 교차 포맷 수치 정밀도", S33_CROSS_NUM),
    ]

    all_scenarios: list[ScenarioReport] = []
    total_cases = 0
    skipped_scenarios = 0

    for name, cases in all_groups:
        hard_cases = filter_hard(cases)
        if not hard_cases:
            skipped_scenarios += 1
            continue

        total_cases += len(hard_cases)
        print(f"\n{SUB_DIVIDER}")
        print(f"  {name} ({len(hard_cases)} hard/extreme)")
        print(SUB_DIVIDER)

        report = ScenarioReport(name=name)
        for tc in hard_cases:
            r = run_test(engine, tc)
            report.results.append(r)
            print_result(r)
        print(f"  >> {report.passed}/{report.total} passed (avg {report.avg_latency:.2f}s)")
        all_scenarios.append(report)

    # S8 multi-turn: only hard turns (8.5, 8.6)
    print(f"\n{SUB_DIVIDER}")
    print("  S8: 멀티턴 대화 (hard turns only)")
    print(SUB_DIVIDER)
    s8 = run_multiturn(engine)
    # Filter to only hard/extreme results
    s8_hard = ScenarioReport(name="S8: 멀티턴 대화")
    s8_hard.results = [r for r in s8.results if r.test_case.difficulty in ("hard", "extreme")]
    if s8_hard.results:
        for r in s8_hard.results:
            print_result(r)
        print(f"  >> {s8_hard.passed}/{s8_hard.total} passed")
        all_scenarios.append(s8_hard)
        total_cases += len(s8_hard.results)

    # Summary
    total = sum(s.total for s in all_scenarios)
    passed = sum(s.passed for s in all_scenarios)

    print(f"\n{DIVIDER}")
    print(f"  FOCUSED RESULTS: {passed}/{total} hard/extreme passed ({passed / total * 100:.1f}%)")
    print(f"  (Skipped {skipped_scenarios} scenarios with no hard/extreme cases)")
    print(DIVIDER)

    for s in all_scenarios:
        status = PASS if s.failed == 0 else FAIL
        print(f"  {status} {s.name}: {s.passed}/{s.total}")

    # Save report
    report_path = PROJECT_ROOT / "docs" / "reports" / "v4" / "hard-only-report.md"
    generate_report(all_scenarios, ingest_info, report_path)

    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)


if __name__ == "__main__":
    main()
