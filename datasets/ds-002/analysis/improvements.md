# Improvements for ds-002

## Applied Fixes

### Fix 1: 짧은 코드 블록 인접 텍스트 병합 (Run 2)
- **Date**: 2026-03-27
- **Target**: `quantumrag/core/utils/text.py`
- **Change**: `split_preserving_blocks()`에서 6줄 이하 코드 블록은 "code" 대신 "text"로 분류하여 인접 텍스트와 합쳐지도록 변경
- **Rationale**: q006 — Variance 코드 블록이 너무 짧아 독립 청크가 되면 컨텍스트 상실
- **Result**: q006 여전히 실패 — 코드 블록 병합만으로는 불충분

### Fix 2: 영어 전문용어 BM25 보조 검색 (Run 3)
- **Date**: 2026-03-27
- **Target**: `quantumrag/core/engine.py` (retrieval retry 로직)
- **Change**: insufficient_evidence retry 시, 쿼리에서 영어 단어(3자+)를 추출하여 BM25 보조 쿼리로 추가 실행. 결과를 0.8 가중치로 retry 청크에 병합.
- **Rationale**: q006 — 한국어 쿼리에 영어 전문용어가 포함될 때 BM25 매칭 강화
- **Result**: q006 여전히 실패 — 해당 청크 자체가 정보 밀도가 너무 낮음

## Remaining Failures (3건)

### q006: TypeVar covariant/contravariant — 해결 불가 (현 아키텍처)
- **Root cause**: 소스에 코드 주석 3줄(`# Covariant (for output/return)`)만 존재
- **상태**: retrieval에서 해당 청크가 top-k에 진입하지 못함
- **필요한 해결책**: 쿼리-문서 간 cross-lingual semantic matching 강화 (큰 아키텍처 변경 필요)

### q007: Protocol vs dataclass "structural" — 평가 기준 문제
- **Root cause**: 엔진은 "구조적 서브타이핑"으로 정확히 답변, 키워드 "structural"만 불일치
- **상태**: 엔진 문제 아님, 평가 개선 필요 (한/영 동의어 매칭)

### q011: 벤처 투자 게이밍 69.4% — 동일 문서 내 섹션 혼동
- **Root cause**: "벤처 투자 성장률" 질의 → "창업 증감률" 테이블이 우선 검색됨
- **상태**: 같은 문서 내 유사 주제 섹션 구분이 어려운 retrieval 한계

## Verified
- `make check`: lint OK, 758 tests passed
- 3 runs completed: 88% → 88% → 88% (안정적)
