# Improvements for ds-001

## Applied Fixes

### Fix 1: 코드 블록 보호 (Code Block Preservation)
- **Date**: 2026-03-27
- **Target**: `quantumrag/core/utils/text.py`, `quantumrag/core/ingest/chunker/fixed.py`, `quantumrag/core/ingest/chunker/semantic.py`
- **Change**:
  - `split_preserving_code_blocks()` 함수 추가 — 테이블 보호와 동일한 패턴으로 fenced code block을 atomic unit으로 보호
  - `split_preserving_blocks()` 함수 추가 — 테이블 + 코드 블록 동시 보호하는 통합 함수
  - FixedSizeChunker, SemanticChunker에서 `split_preserving_tables` → `split_preserving_blocks`로 교체
- **Rationale**: q008 실패 — Counter의 intersection/union 설명이 코드 블록 인라인 주석에만 존재했으나, 코드 블록이 분할되어 retrieval에서 누락됨
- **Verified**: `make check` — lint OK, 758 tests passed (7.43s)
- **Pending**: `/qa-run ds-001`로 q008 통과 여부 재검증 필요
