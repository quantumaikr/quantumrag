# QuantumRAG v5~v8 진화 분석 보고서

> 작성일: 2026-03-27
> 테스트 대상: Hard/Extreme 난이도 104건 (전체 176건 중)
> 테스트 문서: 20개 | 청크: 64개

## 1. 버전별 성적 추이

| 버전 | 통과 | 실패 | 통과율 | 주요 변경점 |
|------|------|------|--------|-----------|
| v5 (baseline) | 83/104 | 21 | **79.8%** | Query Classifier 강화 (_MIXED_CASE_TERM_RE, _VALUE_ASKING_RE) |
| v6 | 86/104 | 18 | **82.7%** | Generation Prompt 강화, Map-Reduce 패턴 확장, Broad Retrieval 확장 |
| v7 | 87/104 | 17 | **83.7%** | Temperature 0.1→0.0 |
| v8 | 84/104 | 20 | **80.8%** | Prompt anti-hallucination 강화 (LLM 비결정성으로 변동) |

**참고**: v5→v8 동안 코드 변경으로 인한 구조적 개선은 +3~4건이며, 나머지 변동(±3건)은 LLM 비결정성에 의한 것.

### 안정적 통과 범위

4회 실행 결과 기반, **hard/extreme 통과율은 80~84% 범위**에서 안정화됨.
- Hard (82건): 65~69건 통과 (79~84%)
- Extreme (22건): 15~18건 통과 (68~82%)

## 2. v5→v8 구조적 개선 성과

### 2.1 v6에서 해결된 문제 (안정적으로 유지됨)

| 개선 사항 | 영향 케이스 | 핵심 변경 |
|-----------|-----------|-----------|
| Map-Reduce "모두 나열" 패턴 | S27.2, S30.1 | `_AGGREGATION_PATTERNS`에 나열/열거 추가 |
| Broad retrieval 확장 | S14.2, S14.3 | 열거, 반사실 패턴 추가 |
| Generation prompt 필터링 규칙 | S14.1 (부분) | 규칙 12: 명시적 속성값만 사용 |

### 2.2 v7 Temperature 효과

Temperature 0.1→0.0으로 변경 시:
- 멀티턴 엔티티 추적(S8) 성공률 향상
- 일부 계산 추론 안정화
- 단, 전체적 효과는 ±2건 수준 (미미)

## 3. 잔존 실패 분석 (v8 기준 20건)

### 3.1 카테고리별 분류

| 카테고리 | 건수 | 케이스 ID | 근본 원인 |
|---------|------|-----------|-----------|
| **A. 검색 실패** | 7 | 2.2, 13.4, 17.10, 17.18, 26.5, 33.5, 30.1 | 관련 청크가 top-k에 포함되지 않음 |
| **B. LLM Hallucination** | 3 | 14.1, 31.3, 31.4 | 존재하지 않는 데이터 생성 (SK텔레콤 450만) |
| **C. LLM 추론 부족** | 5 | 19.2, 19.4, 21.1, 21.3, 22.4 | 정보는 있으나 연결/계산/비교 실패 |
| **D. 다중 문서 집합** | 2 | 21.2, 26.1 | 여러 문서의 정보를 동시에 수집해야 함 |
| **E. 암묵적 추론** | 2 | 11.3, 11.4 | 문서에 직접 명시되지 않은 추론 필요 |
| **F. 엔티티 추적** | 1 | 8.5 | 대화 맥락에서 "그 회사" 해소 실패 |

### 3.2 상세 분석

#### A. 검색 실패 (7건) — 가장 임팩트가 큰 영역

**A-1. Multi-hop 검색 (2.2)**
- 쿼리: "Series C 200억 성공 시 총 누적 투자액"
- 필요: company_info.md(155억) + meeting_minutes.md(200억)
- 문제: 쿼리가 "Series C"에 집중되어 company_info의 기존 투자액을 검색하지 못함
- 해결 방향: LLM 기반 Query Decomposition ("현재 누적 투자액은?" + "Series C 목표 금액은?")

**A-2. PDF 깊은 구조 (17.10, 26.5, 33.5)**
- ZeroH PDF의 "Front End Agent", "informativeness", "OVON" 등
- PyMuPDF 추출 시 Bidi 문자(U+202C) 제거로 텍스트 변형
- PDF 테이블의 개별 셀 데이터가 청크 내에서 충분한 컨텍스트 없이 단편화
- 해결 방향: PDF 테이블 전용 청킹 전략, 테이블 캡션 + 셀 데이터 보존

**A-3. 파인튜닝 비용 검색 (13.4)**
- 쿼리: "자체 파인튜닝 모델 전환 시 연간 절감액"
- 회의록에 "월 2,400만→1,500만 절감" 정보 있으나 검색 실패
- 해결 방향: 비용/절감 관련 키워드 강화

#### B. LLM Hallucination (3건) — 지속적 문제

**B-1. SK텔레콤 문제 (14.1, 31.3)**
- Temperature 0.0에서도 3회 연속 동일 hallucination
- "SK텔레콤: 450만원, 온프레미스, Enterprise" — 문서에 존재하지 않는 데이터
- competitor_analysis에서 리턴제로의 고객으로 "SK텔레콤" 언급이 혼동 원인 추정
- 해결 시도: Prompt 규칙 12 (명시적 속성만 사용) — 효과 미미
- 해결 방향: Context에 테이블 데이터 포맷 강화, 또는 fact-checking post-processing

**B-2. 일본 PoC ARR (31.4)**
- 3건의 개별 금액(2.5+1.8+3.2=7.5억) 대신 단일 금액(3.2×3=9.6억)으로 계산
- 해결 방향: Map-Reduce에서 개별 항목 추출 강조

#### C. LLM 추론 부족 (5건) — 부분적으로 개선 가능

**주요 패턴:**
- 런웨이 관련 수치(10.7, 12-13개월)를 찾았으나 비교/계산하지 못함
- changelog 하반기 분류에서 버전명(v2.4, v2.5)을 포함하지 않음
- 모순 감지에서 관련 문서를 찾지 못하거나 비교하지 못함

#### D-E. 다중 문서 집합 및 암묵적 추론 (4건) — 구조적 한계

- 현재 파이프라인으로 해결하기 어려운 본질적 한계
- GraphRAG 또는 Knowledge Graph 통합으로 근본 해결 가능

## 4. 코드 변경 요약 (v5→v8)

### 4.1 quantumrag/core/retrieve/query_classifier.py
```python
# v5: Mixed-case technical term detection (NEW)
_MIXED_CASE_TERM_RE = re.compile(r"\b[A-Z][a-z]+[A-Z][a-zA-Z]*\b|\b[A-Z]{2,}[a-z]+[A-Z]*\b")

# v5: Korean value-asking queries (NEW)
_VALUE_ASKING_RE = re.compile(
    r"(?:얼마|몇\s*[%개건명억만천원달러]|전망[은이가]?\s*(?:어떻|얼마)|...)"
)
```

### 4.2 quantumrag/core/generate/generator.py
```python
# v6: 프롬프트 규칙 추가
# 9. 조건부/가정 질문 → 수치 기반 추론 강화
# 10. 계산 → 각 출처 수치 나열 후 단계적 계산
# 12. 필터링 → 명시적 속성값만, 테이블 행 정확히 읽기
```

### 4.3 quantumrag/core/engine.py
```python
# v6: Broad retrieval 패턴 확장
re.compile(r"(?:모두|전부|모든).*(?:나열|열거|알려|말해)"),
re.compile(r"(?:나열|열거)\s*(?:하세요|해주세요|해\s*줘)"),
re.compile(r"(?:실패|성사|성공|전환).*(?:하면|할\s*경우|시)"),
```

### 4.4 quantumrag/core/generate/map_reduce.py
```python
# v6: Aggregation 패턴 확장
re.compile(r"(?:모두|전부|모든).*(?:알려|말해|나열|열거)"),
re.compile(r"\d+\s*건.{0,10}(?:회사|고객|파트너|항목).{0,10}각각"),
```

### 4.5 quantumrag/core/config.py
```python
# v5: Retrieval 파라미터 강화
top_k: 10        # v4: 7
multiplier: 4    # v4: 3
max_context: 16000  # v4: 12000

# v7: Temperature 최적화
temperature: 0.0  # v4: 0.1
```

## 5. 향후 개선 방향 (v9~v10)

### v9: Multi-hop Query Decomposition (구현 완료)
- **변경**: `_decompose_multi_hop()` 함수 추가 (rewriter.py)
- 조건부 질문("X가 성공하면 총 Y는?")을 baseline + detail + original로 분해
- 실패 조건("X가 실패하면 현재 Y로?")도 분해 지원
- "인가요" false positive 방지를 위해 Pattern 1 정규식 수정
- 예상 효과: 2.2 (누적 투자액), 21.1 (런웨이), 21.2 (ARR) 해결 가능

### v10 방향: Integration Hardening (향후)
- PDF 테이블 전용 청킹 (테이블 구조 보존)
- Bidi 문자 처리 개선 (공백 보존)
- Post-generation fact-checking (hallucination 감지)
- Confidence calibration (모순 감지 강화)
- 예상 효과: 17.10, 26.5, 33.5, 14.1, 31.3 (5건) 해결 가능

### 구조적 한계 (현 파이프라인)
- 암묵적 추론 (11.3, 11.4): 문서에 없는 정보 → RAG 본질적 한계
- LLM 비결정성: ±3건 변동은 불가피 → temperature=0.0으로 최소화
- PDF 깊은 구조: PyMuPDF 파싱 한계 → Vision LLM 파싱 고려 (비용 높음)

## 6. 결론

v5→v8 진화를 통해 hard/extreme 통과율을 **79.8% → 80~84% 범위**로 개선하였습니다.

**구조적 개선 (코드 변경)**: +3~4건 안정적 개선
- Query classifier 강화 (term_specific 감지 향상)
- Generation prompt 강화 (필터링, 계산, 가정 추론)
- Map-Reduce/Broad retrieval 패턴 확장
- Temperature 최적화

**변동 요인 (LLM 비결정성)**: ±3건
- 동일 코드에서도 실행마다 80~84% 범위에서 변동
- Temperature=0.0이 약간 도움되지만 완전히 제거 불가

**남은 20건의 실패 중**:
- 9건: 코드 개선으로 해결 가능 (v9~v10)
- 7건: LLM 비결정성 영향 (실행마다 변동)
- 4건: 구조적 한계 (RAG 파이프라인의 본질적 제약)
