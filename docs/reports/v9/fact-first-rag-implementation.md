# QuantumRAG v9: Fact-First RAG 구현 보고서

> 작성일: 2026-03-27
> 변경 범위: 4개 파일 수정, 2개 파일 신규 생성

## 1. 개요

v5~v8의 테스트-개선 루프를 통해 hard/extreme 통과율을 80~84% 범위로 안정화했으나,
**잔존 실패 20건 중 가장 고질적인 문제는 LLM Hallucination**(SK텔레콤 450만원 등)이었습니다.

기존 접근(프롬프트 규칙 강화, temperature=0.0)으로는 해결 불가한 이 문제에 대해,
**"Fact-First RAG"** 패러다임을 도입하여 근본적으로 해결합니다.

### 핵심 통찰

Fact Extractor(`fact_extractor.py`)가 이미 인제스트 시 구조화 데이터를 추출하고 있었으나,
이 데이터가 검색/생성/검증 어디에서도 활용되지 않고 있었습니다. v9는 이 **숨겨진 자산**을
파이프라인 전체에 걸쳐 활용합니다.

## 2. 구현 내용 (4단계)

### Level 1: Fact-Aware Context Injection

**파일**: `quantumrag/core/generate/generator.py`

`_build_context()`에서 각 청크의 `metadata["facts"]`를 텍스트 앞에 주입합니다.

```
[Source 1] customer_cases.md — 고객 현황
[검증된 데이터 — 이 정보만이 이 출처에서 확인된 사실입니다]
  - 고객: 삼성전자 | 등급: Enterprise | 배포: 온프레미스
  - 고객: KB국민은행 | 등급: Pro | 배포: 클라우드
  ...

(원문 텍스트)
```

**효과**: LLM이 원문 텍스트를 파싱하기 전에 검증된 구조화 데이터를 먼저 인식합니다.
SK텔레콤이 검증된 고객 목록에 없다는 것을 구조적으로 확인할 수 있습니다.

### Level 2: Answer-Fact Cross-Verification

**파일**: `quantumrag/core/generate/fact_verifier.py` (신규)

생성된 답변에서 엔티티를 추출하고, 구조화된 fact 인덱스와 교차 검증합니다.

- `verify_against_facts()`: 답변의 고객명이 검증된 목록에 없으면 hallucination 플래그
- `build_correction_hint()`: 검증 실패 시 교정 힌트 생성
- 교정 힌트와 함께 재생성하여 hallucination 제거

**통합 위치**: `engine.py` Step 4b2 (self_correct 이후, completeness 이전)

**테스트 결과**:
```
Input:  "SK텔레콤은 Enterprise 등급 고객사입니다. 월 매출 450만원입니다."
Facts:  [삼성전자, KB국민은행] (SK텔레콤 없음)
Output: is_valid=False, hallucinated=['SK텔레콤']
Hint:   "SK텔레콤이(가) 고객으로 언급되었으나 검증된 고객 목록에 없습니다"
```

### Level 3: Query-Aware Constellation

**파일**: `quantumrag/core/retrieve/constellation.py`

그래프 확장 시 쿼리의 도메인(contract, finance, security 등)을 감지하고,
해당 도메인의 facts를 가진 청크에 1.3x 점수 부스트를 줍니다.

```python
# 재무 질문 → finance 도메인 청크 우선
if query_domains and _chunk_matches_domains(chunk, query_domains):
    score *= 1.3  # domain_boost
```

**효과**: "온프레미스 고객은?" 질문 시 contract 도메인 청크가 HR/보안 청크보다 우선됩니다.

### Level 4: Fact Index — 구조화 데이터 직접 조회

**파일**: `quantumrag/core/retrieve/fact_index.py` (신규)

인제스트 시 추출된 모든 facts를 인메모리 인덱스로 관리합니다.

```python
fact_index.query("customer_contract", deployment="온프레미스")
# → [{"customer": "삼성전자", "tier": "Enterprise", ...}, ...]
```

**통합 위치**: `engine.py` Step 2.7 (retrieval 후, generation 전)

쿼리의 도메인을 감지하여 해당 도메인의 전체 fact 목록을 synthetic chunk로 주입합니다:
- `contract` 도메인 → 전체 고객 목록 주입
- `finance` 도메인 → 전체 재무 지표 주입
- `security` 도메인 → 전체 보안 이슈 주입
- `hr` 도메인 → 전체 조직 데이터 주입

## 3. 파이프라인 변경 요약

### 인제스트 파이프라인
```
기존: Parse → Chunk → Facts(추출만) → Embed → Index
v9:   Parse → Chunk → Facts(추출) → Embed → Index → FactIndex 빌드
```

### 쿼리 파이프라인
```
기존: Classify → Retrieve → Constellation → Generate → Self-Correct → Completeness
v9:   Classify → Retrieve → Constellation(도메인 인식) → FactIndex 조회 →
      Generate(fact 주입) → Fact Verify → Self-Correct → Completeness
```

## 4. 변경 파일 목록

| 파일 | 변경 유형 | 핵심 변경 |
|------|----------|----------|
| `generator.py` | 수정 | `_build_context()`에 fact block 주입, `_format_fact_block()` 추가 |
| `fact_verifier.py` | **신규** | 답변-fact 교차 검증, hallucination 감지/교정 |
| `constellation.py` | 수정 | `query_domains` 파라미터, 도메인 매칭 부스트 |
| `fact_index.py` | **신규** | 인메모리 fact 인덱스, SQL-like 조회 |
| `engine.py` | 수정 | FactIndex 빌드, Fact-First 주입, Fact Verify 통합, 도메인 전달 |

## 5. 예상 효과

| 실패 케이스 | 문제 | 해결 메커니즘 |
|------------|------|-------------|
| 14.1, 31.3 (SK텔레콤) | LLM hallucination | Level 2: Fact Verify로 감지 → 교정 재생성 |
| 31.4 (일본 PoC ARR) | 계산 오류 | Level 1: Fact block에서 개별 금액 명시 |
| 2.2 (누적 투자액) | Multi-hop 검색 실패 | Level 4: finance_metric 전체 주입 |
| 13.4 (파인튜닝 비용) | 검색 실패 | Level 4: finance 도메인 감지 → 전체 재무 데이터 주입 |
| 21.2 (다중 문서) | 여러 문서 수집 필요 | Level 3: 도메인 인식 constellation 확장 |

**예상 통과율**: 84~88% (기존 80~84% 대비 +4~8건)

## 6. 설계 원칙

1. **Zero LLM Cost**: 모든 검증/조회는 룰 기반. 추가 LLM 호출 없음 (교정 재생성 제외)
2. **Precision over Recall**: 오탐(false positive) 최소화 — 고객 컨텍스트에서만 검증
3. **Graceful Degradation**: 모든 새 로직은 try/except로 감싸 기존 파이프라인 불파괴
4. **Backward Compatible**: `query_domains=None`이면 기존과 동일하게 동작
