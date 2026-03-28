# QuantumRAG 시나리오 테스트 보고서 v4

> 실행일시: 2026-03-27 08:00:32
> 문서: 20개 | 청크: 64개 | 인제스트: 116.7s
> 혁신 기능: HWPX Paragraph-Aware Parser, Enhanced Retrieval (top_k=10, multiplier=4), Extended Context (16K chars)
> 테스트 구성: S1-S17 (baseline) + S18-S30 (advanced)

## 1. 요약 (Executive Summary)

| 항목 | 결과 |
|------|------|
| 전체 테스트 | 176건 |
| 통과 | 140건 |
| 실패 | 36건 |
| **통과율** | **79.5%** |
| 평균 응답 시간 | 7.61s |
| 최소/최대 응답 시간 | 0.00s / 202.81s |

### 버전 비교 (Baseline vs Advanced vs v4 New)

| 구분 | 테스트 수 | 통과 | 통과율 |
|------|----------|------|--------|
| S1-S17 (Baseline) | 176건 | 140건 | 79.5% |
| S18-S30 (Advanced) | 54건 | 44건 | 81.5% |
| **전체 (v4)** | **176건** | **140건** | **79.5%** |

### 난이도별 통과율

| 난이도 | 통과/전체 | 통과율 |
|--------|----------|--------|
| easy | 16/19 | 84% |
| medium | 42/53 | 79% |
| hard | 65/82 | 79% |
| extreme | 17/22 | 77% |

### 시나리오별 결과

| 시나리오 | 결과 | 통과율 | 평균 응답시간 |
|----------|------|--------|-------------|
| S1: 사실 확인 (기본) | 7/7 (PASS) | 100% | 11.59s |
| S2: 멀티홉 추론 | 6/6 (PASS) | 100% | 14.71s |
| S3: 수치 계산/비교 | 4/6 (FAIL(2)) | 67% | 3.18s |
| S4: 시간/버전 추론 | 5/6 (FAIL(1)) | 83% | 5.12s |
| S5: 부정형/제외 | 5/5 (PASS) | 100% | 6.50s |
| S6: 교차 문서 종합 | 5/5 (PASS) | 100% | 5.15s |
| S7: 패러프레이즈 | 6/6 (PASS) | 100% | 38.23s |
| S8: 멀티턴 대화 (엔티티 추적) | 5/6 (FAIL(1)) | 83% | 5.92s |
| S9: 엣지 케이스 | 6/7 (FAIL(1)) | 86% | 7.10s |
| S10: 정밀 검색 | 6/6 (PASS) | 100% | 4.06s |
| S11: 암묵적 추론 | 3/5 (FAIL(2)) | 60% | 10.77s |
| S12: 경쟁사 비교 | 3/3 (PASS) | 100% | 7.44s |
| S13: 조건부 추론 | 4/5 (FAIL(1)) | 80% | 8.17s |
| S14: 다중 제약 필터링 | 3/5 (FAIL(2)) | 60% | 5.23s |
| S15: 정량적 파생 계산 | 4/5 (FAIL(1)) | 80% | 4.66s |
| S16: 교차 검증 | 3/4 (FAIL(1)) | 75% | 5.07s |
| S17: 다양한 문서 포맷 (PDF/HWPX) | 12/20 (FAIL(8)) | 60% | 7.34s |
| S18: 불완전 정보 추론 | 5/5 (PASS) | 100% | 5.00s |
| S19: 모순/불일치 감지 | 2/4 (FAIL(2)) | 50% | 6.61s |
| S20: 한영 혼합 질의 | 3/4 (FAIL(1)) | 75% | 4.48s |
| S21: 반사실적 추론 | 2/4 (FAIL(2)) | 50% | 6.55s |
| S22: 수치 교차 검증 | 3/4 (FAIL(1)) | 75% | 6.40s |
| S23: 복합 조건부 질의 | 4/4 (PASS) | 100% | 4.71s |
| S24: 추상적/메타 질의 | 3/3 (PASS) | 100% | 5.46s |
| S25: 역방향 추론 | 3/3 (PASS) | 100% | 5.87s |
| S26: 테이블 구조 이해 | 3/5 (FAIL(2)) | 60% | 7.05s |
| S27: 답변 완전성 | 5/5 (PASS) | 100% | 4.97s |
| S28: 청크 경계 강건성 | 3/4 (FAIL(1)) | 75% | 4.70s |
| S29: PDF 심층 구조 추출 | 5/5 (PASS) | 100% | 5.44s |
| S30: 산재 정보 종합 수집 | 3/4 (FAIL(1)) | 75% | 7.72s |
| S31: Reranker 강화 검색 | 2/5 (FAIL(3)) | 40% | 4.57s |
| S32: HWPX 심층 추출 | 3/5 (FAIL(2)) | 60% | 4.12s |
| S33: 교차 포맷 수치 정밀도 | 4/5 (FAIL(1)) | 80% | 7.04s |

## 2. 인제스트 결과

| 항목 | 결과 |
|------|------|
| 문서 수 | 20개 |
| 청크 수 | 64개 |
| 소요 시간 | 116.7s |

## 3. 혁신 기능 영향 분석

### 3.1 Contextual Chunk Enrichment
- 각 청크에 상위 섹션 계층(breadcrumb)을 자동 주입
- 효과: 버전/시간 추론 시나리오(S4)에서 버전 번호-기능 매핑 정확도 향상

### 3.2 Query Decomposition
- 복합 질문을 하위 질문으로 분해하여 병렬 검색
- 효과: 멀티홉(S2), 교차 문서(S6) 시나리오에서 리콜 향상

### 3.3 Entity Memory Tracker
- 대화 중 엔티티를 유형별로 추적 (회사/제품/인물)
- 효과: 멀티턴(S8)에서 '그 회사' -> 퀀텀아이, '그 제품' -> QuantumGuard 정확 해소

## 4. 시나리오별 상세 결과

### S1: 사실 확인 (기본)

- 결과: **7/7** (평균 11.59s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 1.1 | 기본 인물 조회 | easy | ANY | PASS | strongly_supported | 2.3s |
| 1.2 | 기본 수치 조회 | easy | ANY | PASS | strongly_supported | 2.3s |
| 1.3 | 계약서 수치 | easy | ANY | PASS | strongly_supported | 3.0s |
| 1.4 | 제품 버전 날짜 -- 청크 문맥 보강으로 해결 기대 | medium | ANY | PASS | strongly_supported | 2.7s |
| 1.5 | 조직도 수치 | easy | ANY | PASS | strongly_supported | 65.5s |
| 1.6 | 보안 감사 보고서 | easy | ANY | PASS | strongly_supported | 2.4s |
| 1.7 | 고객 사례 보고서 | easy | ANY | PASS | strongly_supported | 2.9s |

### S2: 멀티홉 추론

- 결과: **6/6** (평균 14.71s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 2.1 | 회의록+이메일: 45억 / 4.2억 | medium | ANY | PASS | strongly_supported | 2.7s |
| 2.2 | 155억(기존) + 200억(Series C) = 355억 | hard | ANY | PASS | strongly_supported | 4.2s |
| 2.3 | 조직도에서 박서연 겸임 + 예산 | medium | ALL | PASS | strongly_supported | 4.0s |
| 2.4 | 이메일(HyPE 성능 보고) + changelog 교차 | hard | ANY | PASS | strongly_supported | 5.5s |
| 2.5 | 이메일: 2.5억 + 1.8억 + 3.2억 = 7.5억 | hard | ANY | PASS | strongly_supported | 66.3s |
| 2.6 | 이메일(ARR 180억 필요) + 이메일(하반기 신규 30억) | extreme | ANY | PASS | strongly_supported | 5.6s |

### S3: 수치 계산/비교

- 결과: **4/6** (평균 3.18s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 3.1 | (152-52)/52 = 192% | medium | ANY | PASS | strongly_supported | 2.7s |
| 3.2 | 회의록 비용 구조 | medium | ALL | **FAIL** | insufficient_evidence | 5.2s |
| 3.3 | 조직도: 8+12+4+6.5+2 = 32.5억 | medium | ANY | PASS | strongly_supported | 2.9s |
| 3.4 | 이메일: 7.5/19.5 = 38.5% | hard | ANY | PASS | strongly_supported | 2.7s |
| 3.5 | 고객 사례: 주 8시간 -> 2.5시간 = 5.5시간 절감 | medium | ANY | PASS | strongly_supported | 2.9s |
| 3.6 | 감사 보고서: 심각1+높음3+중간2+낮음0 = 6~7건 조치 완료 / 13건 | hard | ANY | **FAIL** | strongly_supported | 2.6s |

<details><summary>실패 케이스 상세</summary>

**[3.2] 회의록 비용 구조** (medium)
- 질문: 인건비가 전체 비용에서 차지하는 비율과 월 인건비 금액은?
- 기대 키워드 (all): `['65%', '5.8억']`
- 실제 답변: 제공된 컨텍스트에는 **전체 비용(총비용) 대비 인건비 비율**과 **월 인건비 금액**을 계산/확인할 수 있는 데이터가 없습니다. (고객별 매출, 월별 매출 추이, 기술 제안서의 PoC 비용, 정책 일정, 사내 이메일 등은 인건비/총비용 항목을 포함하지 않음) [1], [2], [4]  따라서 요청하신 값은 **산출 불가**입니다.  - 인건비가 전체 비용에서 차지하는 비율: **INSUFFICIENT_EVIDENCE** - 월 인건비 금액: **INSUFFICIENT_EVIDENCE**  **신뢰도: INSUFFICIENT_EV

**[3.6] 감사 보고서: 심각1+높음3+중간2+낮음0 = 6~7건 조치 완료 / 13건** (hard)
- 질문: 보안 감사에서 조치 완료된 비율은 얼마인가요?
- 기대 키워드 (any): `['7', '8', '54%', '62%', '53%']`
- 실제 답변: 보안 감사(총 13건)에서 **조치 완료된 건수는 3건**이며, 따라서 **조치 완료 비율은 3/13 = 약 23.1%**입니다. [1]  - 완료된 항목:     - [SEC-001] API 키 평문 저장 — **2024-09-15 완료** [1]     - [SEC-002] 인증 토큰 만료 시간 과다 — **2024-10-01 완료** [1]     - [SEC-003] SQL Injection 취약점 — **2024-09-20 완료** [1]   - 총계: **13건** [1]  **계산:** 3 ÷ 13 × 100 = **2

</details>

### S4: 시간/버전 추론

- 결과: **5/6** (평균 5.12s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 4.1 | changelog breadcrumb으로 해결 기대 | medium | ANY | PASS | strongly_supported | 3.1s |
| 4.2 | v2.1 -> v2.3 변화 | hard | ANY | PASS | partially_supported | 8.1s |
| 4.3 | v2.4(라우팅, 2024-07) vs v2.5(HyPE, 2024-10) | medium | ANY | PASS | strongly_supported | 2.6s |
| 4.4 | changelog 호환성 섹션 | medium | ANY | PASS | strongly_supported | 2.7s |
| 4.5 | 이메일 + 로드맵 교차 | medium | ANY | PASS | strongly_supported | 2.3s |
| 4.6 | 로드맵 Q1 P0 항목 | medium | ALL | **FAIL** | insufficient_evidence | 11.9s |

<details><summary>실패 케이스 상세</summary>

**[4.6] 로드맵 Q1 P0 항목** (medium)
- 질문: v3.0 Atlas 릴리스에서 가장 높은 우선순위(P0) 기능들은 무엇인가요?
- 기대 키워드 (all): `['OCR', '증분 인덱싱']`
- 실제 답변: 제공된 컨텍스트에는 **v3.0 Atlas 릴리스의 P0(최우선) 기능 목록이 직접적으로 명시되어 있지 않습니다**. 따라서 “가장 높은 우선순위(P0) 기능들”을 확정해서 답할 수는 없습니다. [1][17][18]  다만, v3.0에서 **계획**으로 언급된 기능은 다음입니다.   - **자동 중복 감지 및 증분 업데이트** 지원 예정 [17][18]   - **OCR 통합** 예정(스캔된 PDF 처리 관련) [17]    하지만 이들은 **P0로 지정되었다는 근거는 없습니다**. [17][18]  신뢰도: **INSUFFICIE

</details>

### S5: 부정형/제외

- 결과: **5/5** (평균 6.50s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 5.1 | 경쟁사 분석: 뤼튼만 X | medium | ANY | PASS | strongly_supported | 2.7s |
| 5.2 | 경쟁사 분석 표에서 X 찾기 | medium | ALL | PASS | strongly_supported | 17.5s |
| 5.3 | 보안 감사: 중간 5건 중 2건 완료, 3건 미조치 | hard | ANY | PASS | strongly_supported | 2.7s |
| 5.4 | HyPE는 v2.5.0에서 도입 | medium | ANY | PASS | strongly_supported | 2.7s |
| 5.5 | 특허: PAT-001은 한국만, PAT-002는 PCT 완료 | hard | ANY | PASS | insufficient_evidence | 6.9s |

### S6: 교차 문서 종합

- 결과: **5/5** (평균 5.15s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 6.1 | 고객 사례: Enterprise, 82%, 스캔 PDF/이미지 | hard | ANY | PASS | strongly_supported | 3.8s |
| 6.2 | 이메일(속도 요구) + changelog(BM25 40% 개선) | hard | ANY | PASS | strongly_supported | 4.8s |
| 6.3 | 고객 사례: Upstage에서 전환, NDCG 개선 | hard | ANY | PASS | strongly_supported | 2.9s |
| 6.4 | 이메일(기능/가격) + 특허(PAT-004) | extreme | ANY | PASS | strongly_supported | 6.7s |
| 6.5 | 이메일(80억 R&D) + 로드맵(개발15+영업5+기타10=30명) | hard | ANY | PASS | partially_supported | 7.6s |

### S7: 패러프레이즈

- 결과: **6/6** (평균 38.23s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 7.1 | 보유 현금 45억 (일상적 표현) | easy | ANY | PASS | partially_supported | 3.3s |
| 7.2 | 밸류에이션 (비공식 표현) | medium | ANY | PASS | strongly_supported | 3.5s |
| 7.3 | 보안 감사 Critical/High 항목 (구어체) | hard | ANY | PASS | partially_supported | 6.9s |
| 7.4 | 이메일: NTT 데이터 3.2억 (최대 규모) | medium | ANY | PASS | strongly_supported | 202.8s |
| 7.5 | 특허 포트폴리오 (비격식 질문) | hard | ANY | PASS | partially_supported | 10.0s |
| 7.6 | 고객 사례: 최대 고객 | medium | ANY | PASS | strongly_supported | 2.9s |

### S8: 멀티턴 대화 (엔티티 추적)

- 결과: **5/6** (평균 5.92s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 8.1 | 직접 질문 | easy | ANY | PASS | strongly_supported | 3.3s |
| 8.2 | 대명사 resolve: 그 제품 -> QuantumGuard | medium | ANY | PASS | strongly_supported | 4.5s |
| 8.3 | 문맥 유지: QuantumGuard 개발 | medium | ANY | PASS | strongly_supported | 2.6s |
| 8.4 | 주제 전환 -- 경쟁사 분석 | medium | ANY | PASS | partially_supported | 6.5s |
| 8.5 | 엔티티 추적: 그 회사 -> 퀀텀아이 | hard | ANY | **FAIL** | insufficient_evidence | 13.0s |
| 8.6 | 주제 복귀 + 특허 교차 | hard | ANY | PASS | strongly_supported | 5.6s |

<details><summary>실패 케이스 상세</summary>

**[8.5] 엔티티 추적: 그 회사 -> 퀀텀아이** (hard)
- 질문: 그 회사의 매출은 퀀텀소프트보다 얼마나 더 많나요?
- 기대 키워드 (any): `['28억', '30억']`
- 실제 답변: 제공된 컨텍스트만으로는 **QuantumGuard의 실제 매출**을 확인할 수 없어, QuantumSoft와의 매출 차이를 정확히 비교할 수 없습니다. [3]  확인 가능한 정보는 다음과 같습니다. - QuantumGuard는 **가격 정책 초안**만 있으며, 기본 월 200만원 / 프로 월 500만원 / 엔터프라이즈 별도 협의로 제시되어 있습니다. 다만 이는 **매출 실적이 아니라 가격 초안**입니다. [3] - QuantumSoft의 QuantumRAG 고객 현황 종합 기준 **총 월 매출은 약 8,267만원**, 연 환산 약

</details>

### S9: 엣지 케이스

- 결과: **6/7** (평균 7.10s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 9.1 | 빈 질문 | easy | ANY | PASS | insufficient_evidence | 0.0s |
| 9.2 | 문서에 없는 내용 | easy | ANY | PASS | insufficient_evidence | 4.3s |
| 9.3 | 공격적 어투 + 특수문자 | medium | ANY | PASS | strongly_supported | 7.1s |
| 9.4 | 반복 패턴이 포함된 긴 질문 | medium | ANY | PASS | strongly_supported | 4.1s |
| 9.5 | SQL injection 시도 | easy | ANY | **FAIL** | strongly_supported | 5.8s |
| 9.6 | 문서에 존재하지 않는 상세 정보 | easy | ANY | PASS | insufficient_evidence | 9.0s |
| 9.7 | 미래 예측 (문서에 없음) | easy | ANY | PASS | insufficient_evidence | 19.2s |

<details><summary>실패 케이스 상세</summary>

**[9.5] SQL injection 시도** (easy)
- 질문: SELECT * FROM companies WHERE name='퀀텀소프트'
- 기대 키워드 (any): `[]`
- 실제 답변: ```sql SELECT * FROM companies WHERE name='퀀텀소프트'; ```  - 요청하신 SQL 쿼리는 컨텍스트에 제공된 정보(회사명: 퀀텀소프트)와 일치합니다. [1]

</details>

### S10: 정밀 검색

- 결과: **6/6** (평균 4.06s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 10.1 | 회의록/이메일 깊은 상세 정보 | medium | ALL | PASS | strongly_supported | 2.9s |
| 10.2 | changelog 특정 버전 상세 | medium | ALL | PASS | strongly_supported | 5.0s |
| 10.3 | 조직도 CSV의 특정 행 | easy | ALL | PASS | strongly_supported | 3.1s |
| 10.4 | 보안 감사 SEC-003 상세 | hard | ANY | PASS | strongly_supported | 3.6s |
| 10.5 | 이메일: HyPE 성능 표 | hard | ALL | PASS | strongly_supported | 6.1s |
| 10.6 | 특허 문서 상세 | hard | ALL | PASS | strongly_supported | 3.7s |

### S11: 암묵적 추론

- 결과: **3/5** (평균 10.77s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 11.1 | 특허: PAT-001, 002, 003, 004에 모두 등재 -> 강지훈 4건 | hard | ANY | PASS | strongly_supported | 13.2s |
| 11.2 | 이메일: 3.8억->4.2억 = 0.4억 증가 | hard | ANY | PASS | insufficient_evidence | 8.5s |
| 11.3 | 고객 사례: PoC 실패 시 Upstage 재전환 가능 | hard | ANY | **FAIL** | insufficient_evidence | 12.3s |
| 11.4 | 특허 문서: 현재 정적 링크 사용 -> 동적 링크 변경 필요 | hard | ANY | **FAIL** | insufficient_evidence | 11.6s |
| 11.5 | 특허: AGPL 네트워크 사용 조항 | hard | ANY | PASS | partially_supported | 8.3s |

<details><summary>실패 케이스 상세</summary>

**[11.3] 고객 사례: PoC 실패 시 Upstage 재전환 가능** (hard)
- 질문: 현대자동차 PoC가 실패하면 어떤 경쟁사로 전환할 가능성이 있나요?
- 기대 키워드 (any): `['퀀텀아이', 'Upstage']`
- 실제 답변: 컨텍스트에는 **현대자동차 연구소 PoC가 실패할 경우 전환할 경쟁사**에 대한 정보가 없습니다. 현대자동차 연구소의 계약 정보는 PoC 상태와 이탈 위험도(높음)까지만 제시되어 있고, 대체 경쟁사 후보는 언급되지 않았습니다. [4]  따라서 어떤 경쟁사로 전환할 가능성이 있는지는 **판단할 수 없습니다**. [4]  신뢰도: **INSUFFICIENT_EVIDENCE**

**[11.4] 특허 문서: 현재 정적 링크 사용 -> 동적 링크 변경 필요** (hard)
- 질문: Kiwi 형태소 분석기의 라이선스 리스크는 무엇이고, 현재 문제 상태는?
- 기대 키워드 (any): `['LGPL', '정적 링크', '동적 링크']`
- 실제 답변: 제공된 컨텍스트에는 **Kiwi 형태소 분석기**의 라이선스 조건, 저작권/배포 제한, 또는 관련 분쟁·위반 이슈가 **전혀 언급되어 있지 않습니다**. 따라서 **라이선스 리스크가 무엇인지**와 **현재 문제 상태가 어떤지**를 이 자료만으로는 판단할 수 없습니다. [1][2][3][4][5]  참고로, 컨텍스트에 있는 퀀텀소프트의 약관은 **QuantumRAG 서비스**에 대한 이용조건과 데이터/경업금지 조항을 담고 있을 뿐, Kiwi 형태소 분석기와는 직접 관련이 없습니다. [4]  신뢰도: **INSUFFICIENT_EVID

</details>

### S12: 경쟁사 비교

- 결과: **3/3** (평균 7.44s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 12.1 | 특허: 퀀텀소프트 3건 vs 퀀텀아이 8, 리턴제로 12, 42Maru 5 | hard | ANY | PASS | partially_supported | 4.5s |
| 12.2 | 고객 사례(월 1,200만 계약) + 경쟁사(점유율) | extreme | ANY | PASS | insufficient_evidence | 10.3s |
| 12.3 | 이메일(NTT 경쟁) + 경쟁사 분석(기술 비교) | extreme | ANY | PASS | partially_supported | 7.5s |

### S13: 조건부 추론

- 결과: **4/5** (평균 8.17s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 13.1 | 이메일6: R&D 인력 80억 > 운영 50억 > QuantumGuard 40억 > 일본 30억 | medium | ANY | PASS | strongly_supported | 5.5s |
| 13.2 | 런웨이 10.7개월, Q2 2025까지 약 7-8개월 -> 가능하지만 여유 없음 | hard | ANY | PASS | partially_supported | 11.8s |
| 13.3 | 고객 사례(스캔 PDF 요청) + 로드맵(Q1 OCR 통합) | hard | ANY | PASS | strongly_supported | 4.2s |
| 13.4 | 회의록: 월 2,400만 -> 월 1,500만 절감 (60%), 연 1.8억 | hard | ANY | **FAIL** | insufficient_evidence | 9.4s |
| 13.5 | 현재 ARR 120억 -> 180억 필요 = +60억. 파이프라인 19.5억(이메일) + 28억(회의록) | extreme | ANY | PASS | partially_supported | 9.9s |

<details><summary>실패 케이스 상세</summary>

**[13.4] 회의록: 월 2,400만 -> 월 1,500만 절감 (60%), 연 1.8억** (hard)
- 질문: 자체 파인튜닝 모델로 전환하면 연간 얼마를 절감할 수 있나요?
- 기대 키워드 (any): `['1,500만', '1500만', '60%', '1.8억', '18000']`
- 실제 답변: 제공된 컨텍스트만으로는 **자체 파인튜닝 모델로 전환 시 연간 절감액**을 계산할 수 없습니다.   이유는 컨텍스트에 **현재 사용 중인 모델의 연간 비용**, **자체 파인튜닝 모델의 구축·운영 비용**, 또는 **전환 전후 비용 비교 정보**가 없기 때문입니다. [1][2][3][5]  참고로, 컨텍스트에는 퀀텀소프트의 복리후생, 서비스 요금, SLA, 데이터 보호, 해지 조건 등은 있으나, **파인튜닝 모델 전환 비용/절감액**에 대한 정보는 없습니다. [2][3]  신뢰도: **INSUFFICIENT_EVIDENCE**

</details>

### S14: 다중 제약 필터링

- 결과: **3/5** (평균 5.23s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 14.1 | 삼성전자(800만) + 김앤장(2,000만) = 2,800만 | hard | ANY | **FAIL** | strongly_supported | 3.5s |
| 14.2 | Critical: SEC-001(완료), High: SEC-002,003,004(모두 완료) -- 4개 섹션 동시 검색 필요 | extreme | ALL | **FAIL** | insufficient_evidence | 10.2s |
| 14.3 | PAT-002만 PCT 완료 + 강지훈 발명 | hard | ANY | PASS | strongly_supported | 3.5s |
| 14.4 | 조직도: 백엔드(12명,박서연) + AI(15명,강지훈) | medium | ALL | PASS | strongly_supported | 5.2s |
| 14.5 | changelog: v2.4(7월, Adaptive Query Routing) + v2.5(10월, HyPE) | hard | ALL | PASS | strongly_supported | 3.8s |

<details><summary>실패 케이스 상세</summary>

**[14.1] 삼성전자(800만) + 김앤장(2,000만) = 2,800만** (hard)
- 질문: 온프레미스로 배포된 Enterprise 등급 고객의 월 매출 합계는?
- 기대 키워드 (any): `['2,800만', '2800만']`
- 실제 답변: 온프레미스 배포된 **Enterprise 등급** 고객의 월 매출 합계는 다음과 같습니다.  - 법무법인 김앤장: **2,000만원** (온프레미스, Enterprise) [1]   - 삼성전자 반도체: **800만원** (온프레미스, Enterprise) [1]   - SK텔레콤: **450만원** (온프레미스, Enterprise) [1]    합계: **2,000 + 800 + 450 = 3,250만원** [1]  **출처:** [1] 고객별 매출(고객사별 배포 방식/등급/월 매출)

**[14.2] Critical: SEC-001(완료), High: SEC-002,003,004(모두 완료) -- 4개 섹션 동시 검색 필요** (extreme)
- 질문: 조치 완료된 High 등급 이상 보안 이슈의 ID를 모두 나열하세요
- 기대 키워드 (all): `['SEC-001', 'SEC-002', 'SEC-003', 'SEC-004']`
- 실제 답변: 제공된 컨텍스트만으로는 **“조치 완료된 High 등급 이상 보안 이슈의 ID”**를 식별할 수 없습니다.   이유는 보안 이슈 목록, 각 이슈의 **ID / 등급 / 조치 완료 여부**가 포함된 자료가 없고, [Source 5]는 고객별 매출 시트의 컬럼 정보만 있으며 실제 이슈 데이터는 없습니다. [5]  따라서 해당 ID를 모두 나열할 수 없습니다. [5]  신뢰도: **INSUFFICIENT_EVIDENCE**

</details>

### S15: 정량적 파생 계산

- 결과: **4/5** (평균 4.66s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 15.1 | 인프라: 6.5억/6명=1.08억 > AI: 12/15=0.8 > 백엔드: 8/12=0.67 | hard | ANY | PASS | strongly_supported | 4.2s |
| 15.2 | 김앤장2000+네이버1200+삼성800+KB600+현대600=5200/8267=63% | extreme | ANY | PASS | strongly_supported | 3.0s |
| 15.3 | 52->152억 in 2년, CAGR=(152/52)^0.5-1=71% | extreme | ANY | PASS | strongly_supported | 2.6s |
| 15.4 | 회의록: 인건비 5.8억(65%) + 인프라 0.5억(6%) = 6.3억(71%) | hard | ANY | PASS | strongly_supported | 3.4s |
| 15.5 | ARR 120억 / 32개사 = 3.75억. 또는 회의록: 평균 3,800만원/년 | medium | ANY | **FAIL** | insufficient_evidence | 10.2s |

<details><summary>실패 케이스 상세</summary>

**[15.5] ARR 120억 / 32개사 = 3.75억. 또는 회의록: 평균 3,800만원/년** (medium)
- 질문: 고객사당 평균 연간 계약 규모(ARR/고객수)는 얼마인가요?
- 기대 키워드 (any): `['3.75', '3,800만', '3800만', '120억']`
- 실제 답변: 제공된 컨텍스트에는 **ARR(연간 반복매출)**과 **고객 수**에 대한 정보가 없어, **고객사당 평균 연간 계약 규모(ARR/고객수)**를 계산할 수 없습니다. [1][2][3][4][5][6][7]  신뢰도: **INSUFFICIENT_EVIDENCE**

</details>

### S16: 교차 검증

- 결과: **3/4** (평균 5.07s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 16.1 | CEO: 실질 12~13개월, CFO: 10.7개월 -- 시점/가정 차이 | hard | ALL | PASS | strongly_supported | 4.3s |
| 16.2 | 회의록: 25명(개발15+영업5+기타5), 로드맵: 30명(개발15+영업5+기타10) | hard | ALL | PASS | strongly_supported | 5.3s |
| 16.3 | 이메일5: 정식 출시 Q2 2025 = 로드맵 Q2 2025 QuantumGuard v1.0 | medium | ANY | PASS | strongly_supported | 6.3s |
| 16.4 | 회의록: 약 20억원, 이메일6: 30억원 -- 범위 차이 | hard | ALL | **FAIL** | partially_supported | 4.4s |

<details><summary>실패 케이스 상세</summary>

**[16.4] 회의록: 약 20억원, 이메일6: 30억원 -- 범위 차이** (hard)
- 질문: 일본 법인 설립 비용이 이메일과 회의록에서 다른데, 각각 얼마인가요?
- 기대 키워드 (all): `['20억', '30억']`
- 실제 답변: - **회의록 기준 일본 법인 설립 투자 소요:** 약 **20억원** (법인 설립 + 현지 인력 3명) [1]   - **이메일 기준 일본 법인 설립 비용:** **명시된 금액 없음**. (일본 시장 PoC/일본 법인 설립 관련 언급은 있으나, 설립 “비용” 숫자는 제시되지 않음) [2]  **신뢰도:** PARTIALLY_SUPPORTED

</details>

### S17: 다양한 문서 포맷 (PDF/HWPX)

- 결과: **12/20** (평균 7.34s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 17.1 | PDF: 저자/소속 기본 확인 | easy | ALL | PASS | strongly_supported | 3.6s |
| 17.2 | PDF: 아키텍처 핵심 개념 | medium | ANY | PASS | strongly_supported | 3.7s |
| 17.3 | PDF: COCO dataset 5000 image-caption pairs | medium | ANY | **FAIL** | insufficient_evidence | 9.5s |
| 17.4 | PDF: Image-Caption Similarity Assessment | easy | ANY | PASS | strongly_supported | 2.8s |
| 17.5 | PDF: Metrics for Generation Quality | medium | ALL | **FAIL** | insufficient_evidence | 8.7s |
| 17.6 | PDF: Methodology - triple extraction and alignment | hard | ANY | PASS | strongly_supported | 46.2s |
| 17.7 | PDF: Graph-based Contextual Consistency Comparison | medium | ANY | **FAIL** | insufficient_evidence | 10.6s |
| 17.8 | PDF: MKT assesses knowledge sufficiency, Alignment Test evaluates content alignment | hard | ANY | PASS | strongly_supported | 3.0s |
| 17.9 | PDF: Multi-Agent Collaboration via OVON | medium | ANY | **FAIL** | insufficient_evidence | 5.6s |
| 17.10 | PDF: 3단계 리뷰 구조 | hard | ANY | **FAIL** | insufficient_evidence | 5.9s |
| 17.11 | HWPX: 기본 방향 | easy | ANY | PASS | strongly_supported | 4.5s |
| 17.12 | HWPX: 경제성장률 '25 1.8% | easy | ANY | **FAIL** | insufficient_evidence | 4.0s |
| 17.13 | HWPX: 국가공무원 정원 약 4천 명 감축 | medium | ANY | PASS | strongly_supported | 2.4s |
| 17.14 | HWPX: 모바일 신분증 발급자 400만 명 돌파 | easy | ANY | **FAIL** | insufficient_evidence | 4.8s |
| 17.15 | HWPX: 고향사랑기부제 '24잠정 879억 모금 | medium | ANY | **FAIL** | insufficient_evidence | 4.2s |
| 17.16 | HWPX: '24 18개소->'25 35개소 | medium | ANY | PASS | strongly_supported | 5.7s |
| 17.17 | HWPX: 5개->19개 언어, '25.8. | medium | ALL | PASS | strongly_supported | 2.4s |
| 17.18 | HWPX: 드론/SAR 활용 급경사지 붕괴위험 분석기술 | hard | ANY | PASS | strongly_supported | 4.3s |
| 17.19 | PDF+HWPX: 정보의 정확성과 신뢰성이라는 공통 주제 | extreme | ANY | PASS | insufficient_evidence | 6.2s |
| 17.20 | PDF: Comprehensive Unlearning Techniques -- 할루시네이션 최소화 | hard | ANY | PASS | insufficient_evidence | 8.5s |

<details><summary>실패 케이스 상세</summary>

**[17.3] PDF: COCO dataset 5000 image-caption pairs** (medium)
- 질문: ZeroH에서 할루시네이션 분석에 사용한 데이터셋과 규모는?
- 기대 키워드 (any): `['COCO', '5,000', '5000']`
- 실제 답변: 제공된 컨텍스트만으로는 **ZeroH에서 할루시네이션 분석에 사용한 데이터셋과 규모**를 확인할 수 없습니다. [1]  컨텍스트의 [Source 1]은 문서 제목이 **“ZeroH Hallucination Framework”**라는 점만 보여주고, 실제 데이터셋명이나 규모는 포함하지 않습니다. [1]  따라서 현재로서는 **INSUFFICIENT_EVIDENCE**입니다. [1]

**[17.5] PDF: Metrics for Generation Quality** (medium)
- 질문: ZeroH의 생성 품질 평가 지표 3가지는 무엇인가요?
- 기대 키워드 (all): `['informativeness', 'consistency', 'fluency']`
- 실제 답변: 제공된 컨텍스트에는 **“ZeroH”** 또는 **“생성 품질 평가 지표 3가지”**에 대한 정보가 없습니다. 따라서 해당 지표 3가지를 확인할 수 없습니다. [1][2][3]  신뢰도: **INSUFFICIENT_EVIDENCE**

**[17.7] PDF: Graph-based Contextual Consistency Comparison** (medium)
- 질문: ZeroH에서 그래프 기반 문맥 일관성 비교에 사용하는 네트워크는?
- 기대 키워드 (any): `['RGCN', 'Relational Graph']`
- 실제 답변: 제공된 컨텍스트만으로는 **ZeroH에서 그래프 기반 문맥 일관성 비교에 사용하는 네트워크가 무엇인지 확인할 수 없습니다**. [1]   Source 1은 문서 제목과 섹션 요약만 있고, 해당 네트워크에 대한 구체 정보가 없습니다. [1]  신뢰도: **INSUFFICIENT_EVIDENCE**

**[17.9] PDF: Multi-Agent Collaboration via OVON** (medium)
- 질문: ZeroH에서 에이전트 간 통신에 사용하는 표준 프레임워크는?
- 기대 키워드 (any): `['OVON', 'Open Voice Network']`
- 실제 답변: 제공된 컨텍스트에는 **ZeroH Hallucination Framework에서 에이전트 간 통신에 사용하는 “표준 프레임워크”**가 무엇인지에 대한 정보가 없습니다. [9]에는 ZeroH가 **multi-agent orchestration** 등을 포함한다는 설명만 있고, 에이전트 간 통신 방식/표준 프레임워크(예: 특정 라이브러리나 프로토콜)는 명시되어 있지 않습니다. [9]  따라서 현재로서는 답변을 **확정할 수 없으며**, 컨텍스트에 해당 내용이 추가로 필요합니다. [9]  **신뢰도: INSUFFICIENT_EVIDENC

**[17.10] PDF: 3단계 리뷰 구조** (hard)
- 질문: ZeroH 프레임워크의 리뷰 레벨 구조는?
- 기대 키워드 (any): `['Front End Agent', 'Second Level Reviewer', 'Third Level Reviewer']`
- 실제 답변: 제공된 컨텍스트에는 **“ZeroH 프레임워크의 리뷰 레벨 구조(예: 레벨 1/2/3 같은 단계적 리뷰 체계)”**에 대한 정보가 없습니다. 컨텍스트에서 확인되는 것은 **두 단계 워크플로우( Model Knowledge Test, Alignment Test )**와, 그 외 모듈(예: Triple-Oriented Response Segmentation, Graph-based Contextual Consistency Comparison, Reverse Verification via Triples Reconstruction, Self

**[17.12] HWPX: 경제성장률 '25 1.8%** (easy)
- 질문: 2025년 정부 경제성장률 전망은 얼마인가요?
- 기대 키워드 (any): `['1.8']`
- 실제 답변: 제공된 컨텍스트에는 **2025년 정부(또는 정부의) 경제성장률 전망 수치**가 없습니다. 따라서 얼마인지 **확정해서 답변할 수 없습니다.**    - 회의록(자사/사업계획·재무·기술·해외진출)에는 거시경제 성장률 전망이 포함되어 있지 않습니다. [1]   - 문서 요약/정책 일정표(행정·재난·디지털정부 등)에도 **경제성장률 전망(%)** 항목이 제시되어 있지 않습니다. [2], [4]    **신뢰도: INSUFFICIENT_EVIDENCE**

**[17.14] HWPX: 모바일 신분증 발급자 400만 명 돌파** (easy)
- 질문: 모바일 신분증 발급자 수는 얼마인가요?
- 기대 키워드 (any): `['400만']`
- 실제 답변: 제공된 컨텍스트에는 **모바일 신분증 “발급자 수(명)”**에 대한 수치가 없습니다. 다만 **모바일 주민등록증 시범서비스가 9개 지자체에서 ’24.12.27.~ 진행 중**이고, **’25.4. 전국 전면 개통 추진** 계획이 언급되어 있습니다. [1]  따라서 **모바일 신분증 발급자 수는 컨텍스트만으로는 확인할 수 없습니다.**    - 관련 근거: “모바일 주민등록증 시범서비스(’24.12.27.~, 9개 지자체) … 전국 전면 개통 추진(’25.¼)” [1]  **신뢰도: INSUFFICIENT_EVIDENCE**

**[17.15] HWPX: 고향사랑기부제 '24잠정 879억 모금** (medium)
- 질문: 고향사랑기부제의 2024년 잠정 모금액은 얼마인가요?
- 기대 키워드 (any): `['879억']`
- 실제 답변: 제공된 컨텍스트에는 **고향사랑기부제의 2024년 잠정 모금액**에 대한 정보가 없습니다. 따라서 해당 금액을 확인하거나 계산할 수 없습니다. [1][2][3][4][5][6][7][8][9][10][11][12][13][14][15][16][17][18][19][20][21][22][23][24]  **결론:** 컨텍스트만으로는 고향사랑기부제 2024년 잠정 모금액을 알 수 없습니다.    **신뢰도:** INSUFFICIENT_EVIDENCE

</details>

### S18: 불완전 정보 추론

- 결과: **5/5** (평균 5.00s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 18.1 | 문서에 총 인원/예산은 있으나 1인당 연봉은 없음 -- 부분 정보 인정 필요 | hard | ANY | PASS | insufficient_evidence | 6.0s |
| 18.2 | 조직도에 이름만 있고 성별 정보 없음 | medium | ANY | PASS | insufficient_evidence | 4.6s |
| 18.3 | 학술 논문이므로 실제 배포 사례 없음 | medium | ANY | PASS | insufficient_evidence | 4.8s |
| 18.4 | HWPX에 개별 프로그램 예산은 있으나 총액 합산은 불명확 | hard | ANY | PASS | insufficient_evidence | 3.6s |
| 18.5 | 직접 명시되지 않음 -- 감사 결과에서 간접 추론 가능하나 수치 불가 | hard | ANY | PASS | insufficient_evidence | 5.9s |

### S19: 모순/불일치 감지

- 결과: **2/4** (평균 6.61s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 19.1 | 회의록/이메일 간 날짜 교차 확인 | hard | ALL | PASS | strongly_supported | 3.0s |
| 19.2 | 전체 등급 vs 개별 항목 정합성 검증 | extreme | ANY | **FAIL** | insufficient_evidence | 10.0s |
| 19.3 | 시간적 일관성 확인 | hard | ANY | PASS | partially_supported | 6.9s |
| 19.4 | CEO 12-13개월 vs CFO 10.7개월 | hard | ANY | **FAIL** | partially_supported | 6.5s |

<details><summary>실패 케이스 상세</summary>

**[19.2] 전체 등급 vs 개별 항목 정합성 검증** (extreme)
- 질문: 보안 감사 보고서의 전체 위험도 평가와 개별 항목 분석이 일치하나요?
- 기대 키워드 (any): `['심각', '높음', '4건', '3건']`
- 실제 답변: 컨텍스트만으로는 **보안 감사 보고서의 전체 위험도 평가**와 **개별 항목 분석**이 무엇인지 확인할 수 없어, 두 평가가 일치하는지 판단할 수 없습니다. 제공된 자료는 주로 2025년 주요 업무 추진계획과 서비스 이용약관이며, 보안 감사 보고서의 위험도 총평이나 항목별 분석 내용은 포함되어 있지 않습니다. [1][2][3][4][5]  신뢰도: **INSUFFICIENT_EVIDENCE**

**[19.4] CEO 12-13개월 vs CFO 10.7개월** (hard)
- 질문: CEO 이메일의 낙관적 전망과 CFO 보고서의 보수적 전망 중 구체적 수치 차이는?
- 기대 키워드 (any): `['12', '13', '10.7', '소진율']`
- 실제 답변: CEO 이메일과 CFO 보고서에서 직접 비교 가능한 **구체적 수치 차이**는 다음과 같습니다.  1. **상반기 매출**    - CEO: 상반기 매출 **68억원** 달성, 연간 목표의 **45%** 소화 [1]    - CFO: 직접적인 상반기 매출 수치는 없음 [3]    - 따라서 이 항목은 **CEO 수치만 확인 가능**합니다. [1][3]  2. **하반기 신규 계약 필요액**    - CFO: 하반기 신규 계약 **30억원 이상** 필요 [3]    - CEO: 해당 수치는 제시되지 않음 [1]    - 따라서 이 항

</details>

### S20: 한영 혼합 질의

- 결과: **3/4** (평균 4.48s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 20.1 | 한영 혼합: 기술 용어(영) + 질문(한) | medium | ANY | **FAIL** | insufficient_evidence | 4.7s |
| 20.2 | PDF 기반 영어 기술 용어 + 한국어 문맥 | hard | ANY | PASS | insufficient_evidence | 5.1s |
| 20.3 | 영어 비즈니스 용어 + 한국어 데이터 | medium | ANY | PASS | strongly_supported | 2.6s |
| 20.4 | 기술 용어 혼합 -- 문서에 직접 정보 부족할 수 있음 | hard | ANY | PASS | insufficient_evidence | 5.5s |

<details><summary>실패 케이스 상세</summary>

**[20.1] 한영 혼합: 기술 용어(영) + 질문(한)** (medium)
- 질문: QuantumRAG의 Triple Index Fusion에서 BM25 weight는 기본값이 얼마인가요?
- 기대 키워드 (any): `['0.25', '25%']`
- 실제 답변: 제공된 컨텍스트에는 **Triple Index Fusion에서 BM25 weight(가중치) 기본값**이 얼마인지에 대한 정보가 없습니다. [1], [2]의 문서들에는 Triple Index Fusion의 개념(임베딩 + HyPE + BM25 결합)과 관련 성능/구성은 나오지만, **BM25 weight의 기본값 수치**는 명시되어 있지 않습니다. [1], [2]  따라서 현재로서는 **BM25 weight 기본값을 확인할 수 없습니다.** [1], [2]  **신뢰도: INSUFFICIENT_EVIDENCE**

</details>

### S21: 반사실적 추론

- 결과: **2/4** (평균 6.55s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 21.1 | 런웨이 10.7개월 기반 가정 추론 | hard | ANY | **FAIL** | insufficient_evidence | 10.4s |
| 21.2 | 현재 ARR 120억 + 일본 7.5억 = 127.5억 | extreme | ANY | **FAIL** | partially_supported | 4.6s |
| 21.3 | HyPE 도입 전 성능 수준으로 회귀 가정 | hard | ANY | PASS | partially_supported | 4.6s |
| 21.4 | HWPX: 디지털 플랫폼 연관 사업 식별 | hard | ANY | PASS | strongly_supported | 6.5s |

<details><summary>실패 케이스 상세</summary>

**[21.1] 런웨이 10.7개월 기반 가정 추론** (hard)
- 질문: Series C가 실패하면 현재 런웨이로 언제까지 운영 가능한가요?
- 기대 키워드 (any): `['10.7', '10', '2025']`
- 실제 답변: 제공된 컨텍스트만으로는 **Series C 실패 시 현재 런웨이(현금 보유 기간)**를 계산할 수 없습니다. 현재 런웨이를 산출하려면 최소한 **현재 보유 현금/월간 소진액(또는 월 고정비)** 정보가 필요한데, 컨텍스트에는 해당 수치가 없습니다. [1][2][4]  다만 관련해서 확인되는 정보는 다음뿐입니다: - Series C를 위해 **하반기 신규 계약 30억원 이상**이 필요하다고 보고했습니다. [1] - 제품 출시/매출 목표는 있으나, **현재 런웨이 수치**는 제시되지 않았습니다. [1]  따라서 질문에 대한 직접 답변은

**[21.2] 현재 ARR 120억 + 일본 7.5억 = 127.5억** (extreme)
- 질문: 일본 PoC 3건이 모두 성사되면 ARR에 어떤 영향이 있나요?
- 기대 키워드 (any): `['7.5억', '120억', '127.5']`
- 실제 답변: 컨텍스트상 **일본 PoC 3건의 구체적 목록과 각 건의 ARR 합계는 확인되지 않습니다**. 다만 확인되는 일본 PoC는 **NTT 데이터 1건**이며, 예상 규모는 **연 3.2억원**입니다.[2][3] 따라서 **3건이 모두 성사되면 ARR은 최소 3.2억원 × 3건 = 연 9.6억원 증가**로 추정할 수 있습니다.[2][3]  다만, **나머지 2건의 금액 정보가 없어서 실제 ARR 증가는 9.6억원보다 더 클 수도 있습니다**. 컨텍스트만으로는 3건 전체의 정확한 ARR 영향은 산정할 수 없습니다.[2][3]  신뢰도: *

</details>

### S22: 수치 교차 검증

- 결과: **3/4** (평균 6.40s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 22.1 | 고객 사례 보고서에 명시된 개별 고객 수 vs 전체 32개 | extreme | ANY | PASS | strongly_supported | 9.0s |
| 22.2 | 특허 문서의 날짜 기반 정렬 및 간격 계산 | hard | ANY | PASS | insufficient_evidence | 9.9s |
| 22.3 | 조직도 CSV 합산 vs 회사 소개 수치 비교 | medium | ANY | PASS | strongly_supported | 3.0s |
| 22.4 | changelog에서 하반기 항목 분류 및 집계 | hard | ALL | **FAIL** | strongly_supported | 3.7s |

<details><summary>실패 케이스 상세</summary>

**[22.4] changelog에서 하반기 항목 분류 및 집계** (hard)
- 질문: 2024년 하반기 changelog의 기능 추가 건수와 버그 수정 건수를 각각 알려주세요
- 기대 키워드 (all): `['v2.4', 'v2.5']`
- 실제 답변: 2024년 하반기 changelog의 **기능 추가는 6건**, **버그 수정도 6건**입니다[2].  STRONGLY_SUPPORTED

</details>

### S23: 복합 조건부 질의

- 결과: **4/4** (평균 4.71s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 23.1 | 다중 조건: 배포 방식 + 등급 + 만족도 필터링 | extreme | ANY | PASS | partially_supported | 7.0s |
| 23.2 | 보안 감사: 등급 + 조치 상태 교차 필터 | hard | ANY | PASS | partially_supported | 4.2s |
| 23.3 | 시간 구간별 마일스톤 분류 | hard | ANY | PASS | strongly_supported | 4.1s |
| 23.4 | 매출 + 만족도 이중 조건 필터 | hard | ANY | PASS | strongly_supported | 3.6s |

### S24: 추상적/메타 질의

- 결과: **3/3** (평균 5.46s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 24.1 | 여러 문서에서 리스크 요인 추출 및 우선순위 판단 | extreme | ANY | PASS | partially_supported | 4.1s |
| 24.2 | PDF 전체 요약 -- 학술적 기여 추출 | hard | ANY | PASS | partially_supported | 5.5s |
| 24.3 | HWPX에서 디지털 전환 관련 항목 필터링 | hard | ANY | PASS | strongly_supported | 6.8s |

### S25: 역방향 추론

- 결과: **3/3** (평균 5.87s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 25.1 | 수치에서 역방향으로 원인 추적 | hard | ANY | PASS | partially_supported | 10.6s |
| 25.2 | 수치 -> 문맥 역추적 | medium | ANY | PASS | strongly_supported | 3.8s |
| 25.3 | HWPX: 고향사랑기부제 모금액 역추적 | medium | ANY | PASS | strongly_supported | 3.2s |

### S26: 테이블 구조 이해

- 결과: **3/5** (평균 7.05s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 26.1 | 표의 행/열 교차 조건 필터링 | hard | ANY | **FAIL** | insufficient_evidence | 11.0s |
| 26.2 | 표에서 정렬 + 상위 N 추출 | hard | ANY | PASS | insufficient_evidence | 5.7s |
| 26.3 | 표의 그룹별 집계 비교 | extreme | ANY | PASS | strongly_supported | 6.0s |
| 26.4 | 구조적 데이터의 재구조화 | hard | ALL | PASS | strongly_supported | 2.7s |
| 26.5 | PDF 테이블 내 비교 데이터 추출 | extreme | ANY | **FAIL** | insufficient_evidence | 9.9s |

<details><summary>실패 케이스 상세</summary>

**[26.1] 표의 행/열 교차 조건 필터링** (hard)
- 질문: 경쟁사 비교표에서 온프레미스와 멀티모달을 모두 지원하는 경쟁사는?
- 기대 키워드 (any): `['리턴제로', '퀀텀아이']`
- 실제 답변: 제공된 컨텍스트만으로는 **경쟁사 비교표**의 내용이 없어서, **온프레미스와 멀티모달을 모두 지원하는 경쟁사**를 특정할 수 없습니다. 경쟁사명, 지원 방식(온프레미스/멀티모달) 정보가 컨텍스트에 명시되어 있지 않습니다. [1][2][3][4][5][6][7]  신뢰도: **INSUFFICIENT_EVIDENCE**

**[26.5] PDF 테이블 내 비교 데이터 추출** (extreme)
- 질문: ZeroH 논문의 표에서 각 평가 지표별 최고 성능 모델은?
- 기대 키워드 (any): `['informativeness', 'consistency', 'fluency']`
- 실제 답변: 제공된 컨텍스트만으로는 **ZeroH 논문의 표에 있는 각 평가 지표와 그 최고 성능 모델**을 확인할 수 없습니다. [1]   Source 1에는 논문 제목 요약만 있고, 표의 구체적인 지표/모델 결과가 포함되어 있지 않습니다. [1]  따라서 현재로서는 **INSUFFICIENT_EVIDENCE**입니다. [1]

</details>

### S27: 답변 완전성

- 결과: **5/5** (평균 4.97s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 27.1 | 3건의 산재된 정보 완전 수집 | hard | ANY | PASS | strongly_supported | 3.0s |
| 27.2 | 4개 보안 이슈 완전 열거 | extreme | ALL | PASS | strongly_supported | 7.8s |
| 27.3 | 4개 특허 완전 열거 | hard | ALL | PASS | strongly_supported | 3.8s |
| 27.4 | 4개 항목 완전 열거 + 금액 | hard | ANY | PASS | strongly_supported | 3.2s |
| 27.5 | 4분기 전체 로드맵 완전 수집 | hard | ALL | PASS | strongly_supported | 7.1s |

### S28: 청크 경계 강건성

- 결과: **3/4** (평균 4.70s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 28.1 | 버전 경계에 걸친 정보 추출 | hard | ANY | PASS | strongly_supported | 4.3s |
| 28.2 | 문서 말미의 부가 정보 — 청크 경계에서 누락 가능 | medium | ANY | PASS | insufficient_evidence | 4.6s |
| 28.3 | HWPX 문서 후반부 정보 — 마지막 청크에 위치 | medium | ANY | PASS | strongly_supported | 4.6s |
| 28.4 | PDF 결론부 — 문서 끝부분 청크 경계 | hard | ANY | **FAIL** | insufficient_evidence | 5.3s |

<details><summary>실패 케이스 상세</summary>

**[28.4] PDF 결론부 — 문서 끝부분 청크 경계** (hard)
- 질문: ZeroH 논문의 References 직전 섹션(Conclusion)의 핵심 주장은?
- 기대 키워드 (any): `['hallucination', 'framework', 'future', '결론']`
- 실제 답변: 제공된 컨텍스트에는 **ZeroH 논문에서 “References 직전 섹션(Conclusion)”의 내용**이 포함되어 있지 않습니다. 따라서 **Conclusion의 핵심 주장**을 문서 근거로 특정해 답변할 수 없습니다. [1][2][3]  - 참고로, 컨텍스트에는 ZeroH의 **방법론(2단계: dataset construction + unlearning), 커뮤니티/지원(다중 리뷰 레벨, Conversation Envelopes 등), 인용/검증(RefChecker, 인용 관행, 인간 검토)** 및 **향후 방향**에 대한

</details>

### S29: PDF 심층 구조 추출

- 결과: **5/5** (평균 5.44s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 29.1 | PDF의 Figure/Table 캡션 추출 | hard | ANY | PASS | insufficient_evidence | 4.5s |
| 29.2 | PDF 본문의 분류 체계 추출 | medium | ANY | PASS | strongly_supported | 2.6s |
| 29.3 | PDF Abstract 섹션 정밀 추출 | medium | ANY | PASS | partially_supported | 6.5s |
| 29.4 | PDF 핵심 방법론 완전 열거 | hard | ANY | PASS | partially_supported | 7.1s |
| 29.5 | PDF의 실험 설정 정보 수집 | extreme | ANY | PASS | partially_supported | 6.4s |

### S30: 산재 정보 종합 수집

- 결과: **3/4** (평균 7.72s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 30.1 | 여러 문서에 산재된 파트너 정보 수집 | hard | ANY | **FAIL** | insufficient_evidence | 12.1s |
| 30.2 | 이메일+회의록에 분산된 PoC 정보 종합 | extreme | ANY | PASS | strongly_supported | 6.8s |
| 30.3 | 로드맵+이메일+회의록의 일정 정보 통합 | hard | ANY | PASS | strongly_supported | 7.0s |
| 30.4 | 특허+감사+changelog에 분산된 오픈소스 정보 | extreme | ANY | PASS | partially_supported | 5.0s |

<details><summary>실패 케이스 상세</summary>

**[30.1] 여러 문서에 산재된 파트너 정보 수집** (hard)
- 질문: 퀀텀소프트의 모든 외부 파트너사(투자사, 고객사 제외)를 나열해주세요
- 기대 키워드 (any): `['미래에셋', '한화']`
- 실제 답변: 제공된 컨텍스트만으로는 **퀀텀소프트의 모든 외부 파트너사(투자사, 고객사 제외)**를 확인할 수 없습니다.   - Source 1은 퀀텀소프트의 서비스 약관으로, 외부 파트너사 목록을 포함하지 않습니다. [1]   - Source 2와 Source 4는 행정안전부의 2025년 주요 정책 자료로, 퀀텀소프트의 파트너사 정보와는 관련이 없습니다. [2][4]   - Source 3은 사내 이메일 스레드의 요약만 있고, 구체적인 파트너사 명단은 제시되지 않았습니다. [3]  따라서 현재 컨텍스트로는 외부 파트너사를 나열할 수 없습니다.

</details>

### S31: Reranker 강화 검색

- 결과: **2/5** (평균 4.57s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 31.1 | 이메일 30억 vs 회의록 20억 — reranker로 양쪽 모두 검색 | hard | ALL | **FAIL** | partially_supported | 6.1s |
| 31.2 | CEO 12-13개월 vs CFO 10.7개월 — 교차 문서 수치 검색 | hard | ANY | PASS | strongly_supported | 3.8s |
| 31.3 | 삼성(800)+김앤장(2000)=2800만 계산 | hard | ANY | **FAIL** | strongly_supported | 2.9s |
| 31.4 | 미쓰비시2.5+소프트뱅크1.8+NTT3.2=7.5억 -> 120+7.5=127.5 | extreme | ANY | **FAIL** | strongly_supported | 4.3s |
| 31.5 | 하반기 버전명 구체적 열거 | hard | ALL | PASS | strongly_supported | 5.8s |

<details><summary>실패 케이스 상세</summary>

**[31.1] 이메일 30억 vs 회의록 20억 — reranker로 양쪽 모두 검색** (hard)
- 질문: 일본 법인 설립 비용이 이메일과 회의록에서 다른데, 각각 얼마인가요?
- 기대 키워드 (all): `['30억', '20억']`
- 실제 답변: 일본 법인 설립 비용은 문서마다 다르게 제시되어 있습니다.  - **회의록(2024년 4분기 경영진 회의록, 안건 2: 해외 진출 전략 > 일본 시장)**: 일본 법인 설립 + 현지 인력 3명 포함 **약 20억원**으로 기재되어 있습니다. [1]   - **이메일(2024-09-15, CEO → 전체 임직원)**: 일본 법인 설립 비용이 **별도로 얼마인지 수치가 제시되어 있지 않습니다**(런웨이/채용 확대/일본 법인 설립 비용을 “감안”한다고만 언급). [2]  따라서 “일본 법인 설립 비용”만 놓고 보면, **회의록은 20억원

**[31.3] 삼성(800)+김앤장(2000)=2800만 계산** (hard)
- 질문: 온프레미스 Enterprise 고객의 월 매출 합계를 계산해주세요
- 기대 키워드 (any): `['2,800만', '2800만']`
- 실제 답변: 온프레미스 **Enterprise** 고객의 월 매출(만원) 합계는 다음과 같습니다.  - 법무법인 김앤장: 2,000만원 (온프레미스, Enterprise) [1]   - 삼성전자 반도체: 800만원 (온프레미스, Enterprise) [1]   - SK텔레콤: 450만원 (온프레미스, Enterprise) [1]    계산: 2,000 + 800 + 450 = **3,250만원** [1]  **신뢰도: STRONGLY_SUPPORTED**

**[31.4] 미쓰비시2.5+소프트뱅크1.8+NTT3.2=7.5억 -> 120+7.5=127.5** (extreme)
- 질문: 일본 PoC 3건이 모두 성사되면 ARR에 미치는 영향은?
- 기대 키워드 (any): `['7.5억', '127.5']`
- 실제 답변: 일본 PoC 3건이 모두 **정식 계약으로 전환**된다고 가정하면, 각 PoC의 정식 계약 전환 시 비용은 **연 3.2억원**이며 동일 조건이 유지됩니다. 따라서 ARR 증가는 **3.2억원 × 3건 = 연 9.6억원**입니다. [2]  참고로, PoC 자체 비용도 각 건당 **연 3.2억원**으로 제시되어 있으나, 질문이 ARR 영향이므로 정식 계약 전환 기준으로 계산하는 것이 적절합니다. [2]  신뢰도: **STRONGLY_SUPPORTED**

</details>

### S32: HWPX 심층 추출

- 결과: **3/5** (평균 4.12s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 32.1 | HWPX에서 경제성장률 1.8% 추출 | medium | ANY | **FAIL** | insufficient_evidence | 5.4s |
| 32.2 | HWPX에서 879억 추출 | medium | ANY | **FAIL** | insufficient_evidence | 5.2s |
| 32.3 | HWPX에서 5개→19개 추출 | medium | ALL | PASS | strongly_supported | 2.7s |
| 32.4 | HWPX 후반부 R&D 관련 내용 | hard | ANY | PASS | strongly_supported | 3.9s |
| 32.5 | HWPX 수치와 맥락 함께 추출 | medium | ANY | PASS | partially_supported | 3.4s |

<details><summary>실패 케이스 상세</summary>

**[32.1] HWPX에서 경제성장률 1.8% 추출** (medium)
- 질문: 2025년 정부 경제성장률 전망은 얼마인가요?
- 기대 키워드 (any): `['1.8']`
- 실제 답변: 제공된 컨텍스트에는 **2025년 정부(또는 정부의) 경제성장률 전망 수치**가 없습니다. 따라서 얼마인지 **확정해서 답변할 수 없습니다.**    - 회의록(자사/사업계획·재무·기술·해외진출)에는 거시경제 성장률 전망이 포함되어 있지 않습니다. [1]   - 문서 요약/정책 일정표(행정·재난·디지털정부 등)에도 **경제성장률 전망(%)** 항목이 제시되어 있지 않습니다. [2], [4]    **신뢰도: INSUFFICIENT_EVIDENCE**

**[32.2] HWPX에서 879억 추출** (medium)
- 질문: 고향사랑기부제의 2024년 잠정 모금액은 얼마인가요?
- 기대 키워드 (any): `['879억']`
- 실제 답변: 제공된 컨텍스트에는 **고향사랑기부제의 2024년 잠정 모금액**에 대한 정보가 없습니다. 따라서 해당 금액을 확인할 수 없습니다. [1][2][3][4][5][6][7][8][9][10][11][12][13][14][15][16][17][18][19][20][21][22][23][24]  **신뢰도: INSUFFICIENT_EVIDENCE**

</details>

### S33: 교차 포맷 수치 정밀도

- 결과: **4/5** (평균 7.04s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 33.1 | 산재된 투자사 정보 완전 수집 | hard | ANY | PASS | strongly_supported | 6.1s |
| 33.2 | 이메일+회의록 교차 연결 | extreme | ANY | PASS | partially_supported | 4.6s |
| 33.3 | 보안 감사 데이터 집계 | hard | ANY | PASS | partially_supported | 3.5s |
| 33.4 | PDF 깊은 구조 검색 - reranker 활용 | hard | ANY | PASS | strongly_supported | 10.5s |
| 33.5 | PDF 세부 정보 검색 | hard | ANY | **FAIL** | insufficient_evidence | 10.5s |

<details><summary>실패 케이스 상세</summary>

**[33.5] PDF 세부 정보 검색** (hard)
- 질문: ZeroH에서 에이전트 간 통신에 사용하는 표준은 무엇인가요?
- 기대 키워드 (any): `['OVON', 'Open Voice']`
- 실제 답변: 제공된 컨텍스트에는 **ZeroH Hallucination Framework의 에이전트 간 통신 표준**에 대한 구체 정보가 없습니다. Source 1은 문서 요약만 있고, Source 2~4에도 ZeroH의 통신 표준은 언급되지 않습니다. 따라서 답변할 수 없습니다. [1][2][3][4]  신뢰도: **INSUFFICIENT_EVIDENCE**

</details>

## 5. 고급 시나리오 분석

### 시나리오 카테고리별 분석

- **S18: 불완전 정보 추론**: 5/5 (100%)
  - 불완전 정보 추론 -- 정보 부족 시 적절한 응답 능력
- **S19: 모순/불일치 감지**: 2/4 (50%)
  - 모순/불일치 감지 -- 문서 간 데이터 정합성 검증 능력
- **S20: 한영 혼합 질의**: 3/4 (75%)
  - 한영 혼합 질의 -- 이중 언어 기술 용어 처리 능력
- **S21: 반사실적 추론**: 2/4 (50%)
  - 반사실적 추론 -- 가정 기반 논리적 추론 능력
- **S22: 수치 교차 검증**: 3/4 (75%)
  - 세밀한 수치 교차 검증 -- 수치 데이터 일관성 검증 능력
- **S23: 복합 조건부 질의**: 4/4 (100%)
  - 복합 조건부 질의 -- 다중 필터 조합 처리 능력
- **S24: 추상적/메타 질의**: 3/3 (100%)
  - 추상적/메타 질의 -- 상위 수준 분석 및 요약 능력
- **S25: 역방향 추론**: 3/3 (100%)
  - 역방향 추론 -- 결과에서 원인으로의 역추적 능력
- **S26: 테이블 구조 이해**: 3/5 (60%)
  - 테이블 구조 이해 -- 표의 행/열 교차 분석 및 구조적 데이터 처리 능력
- **S27: 답변 완전성**: 5/5 (100%)
  - 답변 완전성 -- 다중 항목의 완전한 수집 및 열거 능력
- **S28: 청크 경계 강건성**: 3/4 (75%)
  - 청크 경계 강건성 -- 청크 분할 경계에서의 정보 유실 방지 능력
- **S29: PDF 심층 구조 추출**: 5/5 (100%)
  - PDF 심층 구조 추출 -- PDF 내 Figure/Table/섹션 구조 정밀 추출 능력
- **S30: 산재 정보 종합 수집**: 3/4 (75%)
  - 산재 정보 종합 수집 -- 여러 문서에 분산된 정보의 통합 수집 능력

## 6. 체크리스트

- [x] 다종 문서 인제스트 (MD, TXT, CSV, PDF, DOCX, PPTX, XLSX, HWPX)
- [x] 단순 사실 확인 (S1)
- [x] 멀티홉 추론 (S2)
- [ ] 수치 계산/비교 (S3)
- [ ] 시간/버전 추론 (S4)
- [x] 부정형/제외 (S5)
- [x] 교차 문서 종합 (S6)
- [x] 패러프레이즈/구어체 (S7)
- [ ] 멀티턴 엔티티 추적 (S8)
- [ ] 엣지 케이스 (S9)
- [x] 정밀 검색 (S10)
- [ ] 암묵적 추론 (S11)
- [x] 경쟁사 비교 분석 (S12)
- [ ] 다양한 문서 포맷 (S17)
- [x] 불완전 정보 추론 (S18)
- [ ] 모순/불일치 감지 (S19)
- [ ] 한영 혼합 질의 (S20)
- [ ] 반사실적 추론 (S21)
- [ ] 수치 교차 검증 (S22)
- [x] 복합 조건부 질의 (S23)
- [x] 추상적/메타 질의 (S24)
- [x] 역방향 추론 (S25)
- [ ] 테이블 구조 이해 (S26)
- [x] 답변 완전성 (S27)
- [ ] 청크 경계 강건성 (S28)
- [x] PDF 심층 구조 추출 (S29)
- [ ] 산재 정보 종합 수집 (S30)
- [ ] 평균 응답 시간 < 5초
- [x] hard 난이도 통과율 > 60%
- [x] extreme 난이도 통과율 > 40%

## 7. 성능 분석

| 구간 | 건수 | 비율 |
|------|------|------|
| < 2초 | 1건 | 1% |
| 2~4초 | 63건 | 36% |
| > 4초 | 112건 | 64% |

| 신뢰도 | 건수 |
|--------|------|
| insufficient_evidence | 46건 |
| partially_supported | 29건 |
| strongly_supported | 101건 |

## 8. 결론 및 개선 제안

전체 통과율 **79.5%**로 양호하나, 일부 고난이도 케이스에서 개선이 필요합니다.

### Baseline vs Advanced 비교 인사이트

- Baseline(80%)과 Advanced(81%) 통과율이 유사합니다.
- 고급 추론 능력이 기본 능력과 균형을 이루고 있습니다.

### 개선이 필요한 영역

- **S3: 수치 계산/비교**: 4/6 -- [3.2] 회의록 비용 구조, [3.6] 감사 보고서: 심각1+높음3+중간2+낮음0 = 6~7건 조치 완료 / 13건
- **S4: 시간/버전 추론**: 5/6 -- [4.6] 로드맵 Q1 P0 항목
- **S8: 멀티턴 대화 (엔티티 추적)**: 5/6 -- [8.5] 엔티티 추적: 그 회사 -> 퀀텀아이
- **S9: 엣지 케이스**: 6/7 -- [9.5] SQL injection 시도
- **S11: 암묵적 추론**: 3/5 -- [11.3] 고객 사례: PoC 실패 시 Upstage 재전환 가능, [11.4] 특허 문서: 현재 정적 링크 사용 -> 동적 링크 변경 필요
- **S13: 조건부 추론**: 4/5 -- [13.4] 회의록: 월 2,400만 -> 월 1,500만 절감 (60%), 연 1.8억
- **S14: 다중 제약 필터링**: 3/5 -- [14.1] 삼성전자(800만) + 김앤장(2,000만) = 2,800만, [14.2] Critical: SEC-001(완료), High: SEC-002,003,004(모두 완료) -- 4개 섹션 동시 검색 필요
- **S15: 정량적 파생 계산**: 4/5 -- [15.5] ARR 120억 / 32개사 = 3.75억. 또는 회의록: 평균 3,800만원/년
- **S16: 교차 검증**: 3/4 -- [16.4] 회의록: 약 20억원, 이메일6: 30억원 -- 범위 차이
- **S17: 다양한 문서 포맷 (PDF/HWPX)**: 12/20 -- [17.3] PDF: COCO dataset 5000 image-caption pairs, [17.5] PDF: Metrics for Generation Quality, [17.7] PDF: Graph-based Contextual Consistency Comparison, [17.9] PDF: Multi-Agent Collaboration via OVON, [17.10] PDF: 3단계 리뷰 구조, [17.12] HWPX: 경제성장률 '25 1.8%, [17.14] HWPX: 모바일 신분증 발급자 400만 명 돌파, [17.15] HWPX: 고향사랑기부제 '24잠정 879억 모금
- **S19: 모순/불일치 감지**: 2/4 -- [19.2] 전체 등급 vs 개별 항목 정합성 검증, [19.4] CEO 12-13개월 vs CFO 10.7개월
- **S20: 한영 혼합 질의**: 3/4 -- [20.1] 한영 혼합: 기술 용어(영) + 질문(한)
- **S21: 반사실적 추론**: 2/4 -- [21.1] 런웨이 10.7개월 기반 가정 추론, [21.2] 현재 ARR 120억 + 일본 7.5억 = 127.5억
- **S22: 수치 교차 검증**: 3/4 -- [22.4] changelog에서 하반기 항목 분류 및 집계
- **S26: 테이블 구조 이해**: 3/5 -- [26.1] 표의 행/열 교차 조건 필터링, [26.5] PDF 테이블 내 비교 데이터 추출
- **S28: 청크 경계 강건성**: 3/4 -- [28.4] PDF 결론부 — 문서 끝부분 청크 경계
- **S30: 산재 정보 종합 수집**: 3/4 -- [30.1] 여러 문서에 산재된 파트너 정보 수집
- **S31: Reranker 강화 검색**: 2/5 -- [31.1] 이메일 30억 vs 회의록 20억 — reranker로 양쪽 모두 검색, [31.3] 삼성(800)+김앤장(2000)=2800만 계산, [31.4] 미쓰비시2.5+소프트뱅크1.8+NTT3.2=7.5억 -> 120+7.5=127.5
- **S32: HWPX 심층 추출**: 3/5 -- [32.1] HWPX에서 경제성장률 1.8% 추출, [32.2] HWPX에서 879억 추출
- **S33: 교차 포맷 수치 정밀도**: 4/5 -- [33.5] PDF 세부 정보 검색

### 향후 혁신 방향

1. **LLM 기반 Query Decomposition**: 현재 규칙 기반 -> LLM으로 자동 분해
2. **GraphRAG 통합**: 엔티티 관계 그래프로 멀티홉 추론 근본 해결
3. **Adaptive Chunk Size**: 문서 유형별 최적 청크 크기 자동 조정
4. **Cross-lingual Retrieval**: 한영 혼합 쿼리 임베딩 최적화
5. **Semantic Cache**: 유사 쿼리 캐싱으로 반복 질문 속도 10x 향상
6. **Contradiction-aware Generation**: 모순 감지 후 명시적 불일치 보고
7. **Confidence Calibration**: 불완전 정보에 대한 신뢰도 보정 강화
8. **Counterfactual Reasoning Chain**: 가정 기반 추론 체인 구조화
9. **Table-aware Chunking**: 표 구조를 보존하는 청크 분할 전략
10. **Boundary-overlap Retrieval**: 청크 경계 중복 검색으로 정보 유실 방지
