# QA Analysis: ds-003 — Run 1

Date: 2026-03-27
Run: run-7dec533-20260327-220040.yaml

## Summary

- **Pass rate**: 26/30 (86.7%)
- **Graduation threshold**: 75% (3 runs minimum)
- **Status**: 1/3 runs completed, threshold exceeded

| Difficulty | Pass Rate |
|-----------|-----------|
| easy | 4/5 (80%) |
| hard | 10/12 (83%) |
| extreme | 12/13 (92%) |

## Failure Breakdown

| ID | Category | Description |
|----|----------|-------------|
| q003 | format_issue | "Input" 단계 누락 — 3/4 키워드만 매칭 |
| q006 | format_issue | LaTeX `O(n^2 · d)` 형식 — `n²` 키워드 불일치 |
| q013 | retrieval_miss | Naive RAG 한계점 청크 미검색 (insufficient_evidence) |
| q025 | hallucination_test_fail | 엔진이 추론으로 답변 — insufficient 미반환 |

## Improvement Actions

### Action 1: q003, q006 — 키워드 매칭 완화 (평가 개선)
- q003: "Input" 대신 "입력" 추가 or match_mode를 any로 변경
- q006: `n^2`, `n²`, `O(n` 등 다양한 표기 추가

### Action 2: q013 — Naive RAG 한계점 retrieval 실패
- 소스 006.md에 명확히 존재하나 검색 미스
- 청크 분할 시 해당 섹션이 다른 내용과 혼합될 가능성

### Action 3: q025 — 환각 테스트 한계
- 소스에 명확히 부정/긍정 언급이 없는 질문에 대해 엔진이 추론
- 현 아키텍처에서 "없는 정보에 대한 추론 억제"는 본질적으로 어려움
