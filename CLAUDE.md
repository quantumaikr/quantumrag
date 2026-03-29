# QuantumRAG — AI 개발 가이드

## 프로젝트 개요
Index-Heavy, Query-Light RAG 엔진. Python 3.10+, Apache 2.0.

## 필수 규칙

### 코드 변경 시
- 500MB 이상 오픈소스 모델 사용 금지
- `.env`, API 키, 시크릿은 절대 커밋하지 않음

### 아키텍처 경계
- `api/`, `cli/` → `engine.py`를 통해서만 core 접근 (core 내부 모듈 직접 import 금지)
- 새 파일 생성보다 기존 파일 수정 우선
- 모든 새 로직은 try/except로 감싸서 기존 파이프라인 불파괴

### RAG 파이프라인 규칙
- temperature: 0.0 (변경 금지)
- fact_extractor로 추출된 facts는 retrieval과 generation 양쪽에서 활용할 것
- 프롬프트 변경 시 반드시 시나리오 테스트 영향 검토
- hallucination 방지: fact_verifier (hard gate) + 프롬프트 규칙 (soft gate) 이중 방벽 유지

### 테스트 전략 (단계별 검증)
- **작업 중**: `make quick` — lint만 (0.1초). 코드 수정할 때마다 돌리지 않아도 됨
- **기능 단위 완료 시**: `make smoke` — lint + 핵심 테스트 (2초)
- **변경 영역별**: `make test-gen`, `make test-ret`, `make test-ingest`, `make test-api` — 수정한 영역만
- **커밋/PR 전**: `make check` — lint + 전체 유닛 테스트 (7초)
- **푸시 전 (필수)**: `make check` 통과 확인. lint 에러 또는 테스트 실패가 있으면 푸시 금지
- **파이프라인 변경 후**: `make scenario-test` — 시나리오 통과율 80% 이상 유지 (현재 80~84%)
- `make help`로 전체 명령어 확인

### QA 데이터세트 검증 루프
- `/qa-create` → 웹 소스 수집 + 질문 생성 → `datasets/ds-XXX/`
- `/qa-run ds-XXX` → RAG 실행 + 채점 → `datasets/ds-XXX/runs/`
- `/qa-analyze ds-XXX` → 실패 분석 + 개선안 도출 → `datasets/ds-XXX/analysis/`
- `/qa-improve ds-XXX` → 분석 기반 파이프라인 개선 구현 + 검증
- 직접 실행: `.venv/bin/python datasets/run_qa.py ds-XXX`
- 전체 현황: `datasets/STATUS.md` (run 후 자동 갱신)
- 데이터세트는 생성 후 불변 (소스, 질문 수정 금지)
- 졸업 조건 충족 시 자동으로 status → graduated, .rag_data 삭제
- QA runner 최적화: ingest 캐시, 쿼리당 120초 타임아웃, 동시 3개 병렬 실행
- **Combined QA**: `.venv/bin/python datasets/run_qa_combined.py` — 전체 소스 합산 후 retrieval 정밀도 검증

### 현재 성능 현황
- **개별 QA** (4 datasets, 105 questions): 77~100% pass rate → 전체 graduated
- **Combined QA** (73 sources + 50 noise, 436 chunks): **75% pass rate** (full mode), timeout 2건, 30초 avg
- **개선 이력**: 29% → 65% → **75%** (BM25 정규화 + coherence boost + reranker 블렌딩 + HyPE)
- **남은 실패**: 26건 — retrieval FAIL 23건, timeout 2건, generation FAIL 1건
- **Ceiling 분석**: fusion 가중치 튜닝은 소진됨. 다음 돌파구는 embedding 모델 교체 또는 노이즈 축소
- **기본 LLM**: gemini-3.1-flash-lite-preview (무료 티어, 비용 효율적)

## 주요 파일 위치
- 엔진 진입점: `quantumrag/core/engine.py`
- RAG 설정: `quantumrag/core/config.py`
- 생성 프롬프트: `quantumrag/core/generate/generator.py` (_SYSTEM_PROMPT_KO)
- Fact 추출: `quantumrag/core/ingest/indexer/fact_extractor.py`
- Fact 검증: `quantumrag/core/generate/fact_verifier.py`
- 쿼리 분류: `quantumrag/core/retrieve/query_classifier.py`
- 시나리오 테스트: `tests/scenarios/v4/test_cases.py` (176건)
- QA 데이터셋: `datasets/` (4 datasets, 105 questions)
- QA 러너: `datasets/run_qa.py` (개별), `datasets/run_qa_combined.py` (합산)
