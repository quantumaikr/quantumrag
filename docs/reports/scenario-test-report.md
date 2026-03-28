# QuantumRAG 시나리오 테스트 보고서 v2

> 실행일시: 2026-03-28 15:46:20
> 문서: 20개 | 청크: 262개 | 인제스트: 167.7s
> 혁신 기능: Contextual Chunk Enrichment, Query Decomposition, Entity Memory Tracker

## 1. 요약 (Executive Summary)

| 항목 | 결과 |
|------|------|
| 전체 테스트 | 107건 |
| 통과 | 97건 |
| 실패 | 10건 |
| **통과율** | **90.7%** |
| 평균 응답 시간 | 8.68s |
| 최소/최대 응답 시간 | 0.00s / 93.82s |

### 난이도별 통과율

| 난이도 | 통과/전체 | 통과율 |
|--------|----------|--------|
| easy | 19/19 | 100% |
| medium | 34/38 | 89% |
| hard | 35/41 | 85% |
| extreme | 9/9 | 100% |

### 시나리오별 결과

| 시나리오 | 결과 | 통과율 | 평균 응답시간 |
|----------|------|--------|-------------|
| S1: 사실 확인 (기본) | 7/7 (PASS) | 100% | 3.23s |
| S2: 멀티홉 추론 | 4/6 (FAIL(2)) | 67% | 6.67s |
| S3: 수치 계산/비교 | 6/6 (PASS) | 100% | 3.65s |
| S4: 시간/버전 추론 | 6/6 (PASS) | 100% | 6.42s |
| S5: 부정형/제외 | 5/5 (PASS) | 100% | 3.95s |
| S6: 교차 문서 종합 | 5/5 (PASS) | 100% | 5.15s |
| S7: 패러프레이즈 | 6/6 (PASS) | 100% | 10.76s |
| S8: 멀티턴 대화 (엔티티 추적) | 5/6 (FAIL(1)) | 83% | 4.73s |
| S9: 엣지 케이스 | 7/7 (PASS) | 100% | 10.22s |
| S10: 정밀 검색 | 6/6 (PASS) | 100% | 16.17s |
| S11: 암묵적 추론 | 3/5 (FAIL(2)) | 60% | 17.66s |
| S12: 경쟁사 비교 | 3/3 (PASS) | 100% | 11.00s |
| S13: 조건부 추론 | 5/5 (PASS) | 100% | 10.95s |
| S14: 다중 제약 필터링 | 5/5 (PASS) | 100% | 8.03s |
| S15: 정량적 파생 계산 | 5/5 (PASS) | 100% | 6.31s |
| S16: 교차 검증 | 3/4 (FAIL(1)) | 75% | 5.49s |
| S17: 다양한 문서 포맷 (PDF/HWPX) | 16/20 (FAIL(4)) | 80% | 11.43s |

## 2. 인제스트 결과

| 항목 | 결과 |
|------|------|
| 문서 수 | 20개 |
| 청크 수 | 262개 |
| 소요 시간 | 167.7s |

## 3. 혁신 기능 영향 분석

### 3.1 Contextual Chunk Enrichment
- 각 청크에 상위 섹션 계층(breadcrumb)을 자동 주입
- 효과: 버전/시간 추론 시나리오(S4)에서 버전 번호-기능 매핑 정확도 향상

### 3.2 Query Decomposition
- 복합 질문을 하위 질문으로 분해하여 병렬 검색
- 효과: 멀티홉(S2), 교차 문서(S6) 시나리오에서 리콜 향상

### 3.3 Entity Memory Tracker
- 대화 중 엔티티를 유형별로 추적 (회사/제품/인물)
- 효과: 멀티턴(S8)에서 '그 회사' → 퀀텀아이, '그 제품' → QuantumGuard 정확 해소

## 4. 시나리오별 상세 결과

### S1: 사실 확인 (기본)

- 결과: **7/7** (평균 3.23s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 1.1 | 기본 인물 조회 | easy | ANY | PASS | strongly_supported | 5.1s |
| 1.2 | 기본 수치 조회 | easy | ANY | PASS | strongly_supported | 2.5s |
| 1.3 | 계약서 수치 | easy | ANY | PASS | strongly_supported | 4.2s |
| 1.4 | 제품 버전 날짜 — 청크 문맥 보강으로 해결 기대 | medium | ANY | PASS | strongly_supported | 2.8s |
| 1.5 | 조직도 수치 | easy | ANY | PASS | strongly_supported | 3.0s |
| 1.6 | 보안 감사 보고서 | easy | ANY | PASS | strongly_supported | 3.0s |
| 1.7 | 고객 사례 보고서 | easy | ANY | PASS | strongly_supported | 2.0s |

### S2: 멀티홉 추론

- 결과: **4/6** (평균 6.67s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 2.1 | 회의록+이메일: 45억 / 4.2억 | medium | ANY | PASS | strongly_supported | 3.3s |
| 2.2 | 155억(기존) + 200억(Series C) = 355억 | hard | ANY | **FAIL** | strongly_supported | 13.6s |
| 2.3 | 조직도에서 박서연 겸임 + 예산 | medium | ALL | PASS | strongly_supported | 4.8s |
| 2.4 | 이메일(HyPE 성능 보고) + changelog 교차 | hard | ANY | PASS | strongly_supported | 7.4s |
| 2.5 | 이메일: 2.5억 + 1.8억 + 3.2억 = 7.5억 | hard | ANY | **FAIL** | strongly_supported | 3.7s |
| 2.6 | 이메일(ARR 180억 필요) + 이메일(하반기 신규 30억) | extreme | ANY | PASS | strongly_supported | 7.2s |

<details><summary>실패 케이스 상세</summary>

**[2.2] 155억(기존) + 200억(Series C) = 355억** (hard)
- 질문: Series C 200억원이 성공하면 총 누적 투자액은 얼마인가요?
- 기대 키워드 (any): `['355억', '355']`
- 실제 답변: Series C 200억원이 성공하면, 컨텍스트상 기존 투자액이 **3억원**으로 확인되므로 총 누적 투자액은 **203억원**입니다. [1]  계산: - 기존 투자액: 3억원 [1] - Series C 투자액: 200억원 [5], [11], [21] - 총 누적 투자액 = 3억원 + 200억원 = **203억원** [1], [5], [11], [21]  신뢰도: **STRONGLY_SUPPORTED**

**[2.5] 이메일: 2.5억 + 1.8억 + 3.2억 = 7.5억** (hard)
- 질문: 일본 시장 PoC 3건의 총 예상 연 계약 규모는 얼마인가요?
- 기대 키워드 (any): `['7.5억', '7억5']`
- 실제 답변: 일본 시장 PoC 3건의 총 예상 연 계약 규모는 **3.2억원/년**입니다.   이는 동일한 수치로 제시된 **연 3.2억원**과 **3.2억원/년**을 종합한 결과입니다 [4][30].  **종합 답변: 3.2억원/년**   **신뢰도: STRONGLY_SUPPORTED**

</details>

### S3: 수치 계산/비교

- 결과: **6/6** (평균 3.65s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 3.1 | (152-52)/52 = 192% | medium | ANY | PASS | strongly_supported | 4.0s |
| 3.2 | 회의록 비용 구조 | medium | ALL | PASS | strongly_supported | 3.1s |
| 3.3 | 조직도: 8+12+4+6.5+2 = 32.5억 | medium | ANY | PASS | strongly_supported | 3.8s |
| 3.4 | 이메일: 7.5/19.5 ≈ 38.5% | hard | ANY | PASS | strongly_supported | 2.7s |
| 3.5 | 고객 사례: 주 8시간 → 2.5시간 = 5.5시간 절감 | medium | ANY | PASS | strongly_supported | 4.2s |
| 3.6 | 감사 보고서: 심각1+높음3+중간2+낮음0 = 6~7건 조치 완료 / 13건 | hard | ANY | PASS | partially_supported | 4.0s |

### S4: 시간/버전 추론

- 결과: **6/6** (평균 6.42s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 4.1 | changelog breadcrumb으로 해결 기대 | medium | ANY | PASS | strongly_supported | 2.0s |
| 4.2 | v2.1 → v2.3 변화 | hard | ANY | PASS | partially_supported | 5.0s |
| 4.3 | v2.4(라우팅, 2024-07) vs v2.5(HyPE, 2024-10) | medium | ANY | PASS | strongly_supported | 4.4s |
| 4.4 | changelog 호환성 섹션 | medium | ANY | PASS | strongly_supported | 4.0s |
| 4.5 | 이메일 + 로드맵 교차 | medium | ANY | PASS | strongly_supported | 3.2s |
| 4.6 | 로드맵 Q1 P0 항목 | medium | ALL | PASS | strongly_supported | 19.8s |

### S5: 부정형/제외

- 결과: **5/5** (평균 3.95s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 5.1 | 경쟁사 분석: 뤼튼만 ✗ | medium | ANY | PASS | strongly_supported | 3.6s |
| 5.2 | 경쟁사 분석 표에서 ✗ 찾기 | medium | ALL | PASS | strongly_supported | 3.0s |
| 5.3 | 보안 감사: 중간 5건 중 2건 완료, 3건 미조치 | hard | ANY | PASS | partially_supported | 2.9s |
| 5.4 | HyPE는 v2.5.0에서 도입 | medium | ANY | PASS | strongly_supported | 3.1s |
| 5.5 | 특허: PAT-001은 한국만, PAT-002는 PCT 완료 | hard | ANY | PASS | partially_supported | 7.0s |

### S6: 교차 문서 종합

- 결과: **5/5** (평균 5.15s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 6.1 | 고객 사례: Enterprise, 82%, 스캔 PDF/이미지 | hard | ANY | PASS | strongly_supported | 3.4s |
| 6.2 | 이메일(속도 요구) + changelog(BM25 40% 개선) | hard | ANY | PASS | partially_supported | 4.3s |
| 6.3 | 고객 사례: Upstage에서 전환, NDCG 개선 | hard | ANY | PASS | strongly_supported | 3.1s |
| 6.4 | 이메일(기능/가격) + 특허(PAT-004) | extreme | ANY | PASS | partially_supported | 10.3s |
| 6.5 | 이메일(80억 R&D) + 로드맵(개발15+영업5+기타10=30명) | hard | ANY | PASS | partially_supported | 4.6s |

### S7: 패러프레이즈

- 결과: **6/6** (평균 10.76s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 7.1 | 보유 현금 45억 (일상적 표현) | easy | ANY | PASS | strongly_supported | 2.7s |
| 7.2 | 밸류에이션 (비공식 표현) | medium | ANY | PASS | strongly_supported | 2.8s |
| 7.3 | 보안 감사 Critical/High 항목 (구어체) | hard | ANY | PASS | insufficient_evidence | 42.6s |
| 7.4 | 이메일: NTT 데이터 3.2억 (최대 규모) | medium | ANY | PASS | strongly_supported | 5.4s |
| 7.5 | 특허 포트폴리오 (비격식 질문) | hard | ANY | PASS | partially_supported | 8.5s |
| 7.6 | 고객 사례: 최대 고객 | medium | ANY | PASS | strongly_supported | 2.6s |

### S8: 멀티턴 대화 (엔티티 추적)

- 결과: **5/6** (평균 4.73s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 8.1 | 직접 질문 | easy | ANY | PASS | strongly_supported | 2.6s |
| 8.2 | 대명사 resolve: 그 제품 → QuantumGuard | medium | ANY | PASS | strongly_supported | 4.2s |
| 8.3 | 문맥 유지: QuantumGuard 개발 | medium | ANY | **FAIL** | strongly_supported | 2.6s |
| 8.4 | 주제 전환 — 경쟁사 분석 | medium | ANY | PASS | partially_supported | 4.1s |
| 8.5 | 엔티티 추적: 그 회사 → 퀀텀아이 | hard | ANY | PASS | partially_supported | 5.4s |
| 8.6 | 주제 복귀 + 특허 교차 | hard | ANY | PASS | partially_supported | 9.5s |

<details><summary>실패 케이스 상세</summary>

**[8.3] 문맥 유지: QuantumGuard 개발** (medium)
- 질문: 개발에 몇 명이 추가로 필요한가요?
- 기대 키워드 (any): `['4명']`
- 실제 답변: 컨텍스트에 따르면, **QuantumRAG 개발에 추가로 필요한 인원 수는 “15명”**입니다. [13]  - [13]에 “채용: 개발 15명 + 영업 5명 + 기타 10명 = 총 30명”이라고 명시되어 있습니다. 따라서 개발(추가 필요 인력)은 **15명**입니다. [13]  **신뢰도: STRONGLY_SUPPORTED**

</details>

### S9: 엣지 케이스

- 결과: **7/7** (평균 10.22s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 9.1 | 빈 질문 | easy | ANY | PASS | insufficient_evidence | 0.0s |
| 9.2 | 문서에 없는 내용 | easy | ANY | PASS | insufficient_evidence | 5.1s |
| 9.3 | 공격적 어투 + 특수문자 | medium | ANY | PASS | strongly_supported | 34.8s |
| 9.4 | 반복 패턴이 포함된 긴 질문 | medium | ANY | PASS | partially_supported | 6.8s |
| 9.5 | SQL injection 시도 | easy | ANY | PASS | insufficient_evidence | 0.0s |
| 9.6 | 문서에 존재하지 않는 상세 정보 | easy | ANY | PASS | strongly_supported | 19.1s |
| 9.7 | 미래 예측 (문서에 없음) | easy | ANY | PASS | insufficient_evidence | 5.8s |

### S10: 정밀 검색

- 결과: **6/6** (평균 16.17s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 10.1 | 회의록/이메일 깊은 상세 정보 | medium | ALL | PASS | strongly_supported | 2.5s |
| 10.2 | changelog 특정 버전 상세 | medium | ALL | PASS | strongly_supported | 82.1s |
| 10.3 | 조직도 CSV의 특정 행 | easy | ALL | PASS | strongly_supported | 2.6s |
| 10.4 | 보안 감사 SEC-003 상세 | hard | ANY | PASS | strongly_supported | 3.2s |
| 10.5 | 이메일: HyPE 성능 표 | hard | ALL | PASS | strongly_supported | 3.0s |
| 10.6 | 특허 문서 상세 | hard | ALL | PASS | strongly_supported | 3.6s |

### S11: 암묵적 추론

- 결과: **3/5** (평균 17.66s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 11.1 | 특허: PAT-001, 002, 003, 004에 모두 등재 → 강지훈 4건 | hard | ANY | PASS | strongly_supported | 3.7s |
| 11.2 | 이메일: 3.8억→4.2억 = 0.4억 증가 | hard | ANY | PASS | insufficient_evidence | 8.1s |
| 11.3 | 고객 사례: PoC 실패 시 Upstage 재전환 가능 | hard | ANY | **FAIL** | insufficient_evidence | 46.7s |
| 11.4 | 특허 문서: 현재 정적 링크 사용 → 동적 링크 변경 필요 | hard | ANY | **FAIL** | insufficient_evidence | 26.1s |
| 11.5 | 특허: AGPL 네트워크 사용 조항 | hard | ANY | PASS | strongly_supported | 3.7s |

<details><summary>실패 케이스 상세</summary>

**[11.3] 고객 사례: PoC 실패 시 Upstage 재전환 가능** (hard)
- 질문: 현대자동차 PoC가 실패하면 어떤 경쟁사로 전환할 가능성이 있나요?
- 기대 키워드 (any): `['퀀텀아이', 'Upstage']`
- 실제 답변: 현대자동차 PoC가 실패했을 때 **어느 경쟁사로 전환할 가능성이 있는지**에 대한 정보는, 제공된 컨텍스트에서 **명시적으로 확인되지 않습니다**. 현대자동차 관련 내용은 PoC/신규 PoC, 온프레미스 배포 요청, 고객 등급 정보만 있으며, **전환 대상 경쟁사**는 제시되어 있지 않습니다 [1][2][7][8][11].  따라서 답변은 **INSUFFICIENT_EVIDENCE**입니다.  신뢰도: **INSUFFICIENT_EVIDENCE**

**[11.4] 특허 문서: 현재 정적 링크 사용 → 동적 링크 변경 필요** (hard)
- 질문: Kiwi 형태소 분석기의 라이선스 리스크는 무엇이고, 현재 문제 상태는?
- 기대 키워드 (any): `['LGPL', '정적 링크', '동적 링크']`
- 실제 답변: 제공된 컨텍스트에는 **Kiwi 형태소 분석기의 라이선스 리스크**에 대한 정보가 없습니다. 따라서 리스크가 무엇인지와 현재 문제 상태를 **판단할 수 없습니다**. **INSUFFICIENT_EVIDENCE** [1][2][3][4][5][6]  신뢰도: **INSUFFICIENT_EVIDENCE**

</details>

### S12: 경쟁사 비교

- 결과: **3/3** (평균 11.00s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 12.1 | 특허: 퀀텀소프트 3건 vs 퀀텀아이 8, 리턴제로 12, 42Maru 5 | hard | ANY | PASS | strongly_supported | 3.1s |
| 12.2 | 고객 사례(월 1,200만 계약) + 경쟁사(점유율) | extreme | ANY | PASS | partially_supported | 23.9s |
| 12.3 | 이메일(NTT 경쟁) + 경쟁사 분석(기술 비교) | extreme | ANY | PASS | partially_supported | 6.0s |

### S13: 조건부 추론

- 결과: **5/5** (평균 10.95s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 13.1 | 이메일6: R&D 인력 80억 > 운영 50억 > QuantumGuard 40억 > 일본 30억 | medium | ANY | PASS | strongly_supported | 23.5s |
| 13.2 | 런웨이 10.7개월, Q2 2025까지 약 7-8개월 → 가능하지만 여유 없음 | hard | ANY | PASS | insufficient_evidence | 7.3s |
| 13.3 | 고객 사례(스캔 PDF 요청) + 로드맵(Q1 OCR 통합) | hard | ANY | PASS | strongly_supported | 2.9s |
| 13.4 | 회의록: 월 2,400만 → 월 1,500만 절감 (60%), 연 1.8억 | hard | ANY | PASS | strongly_supported | 11.4s |
| 13.5 | 현재 ARR 120억 → 180억 필요 = +60억. 파이프라인 19.5억(이메일) + 28억(회의록) | extreme | ANY | PASS | insufficient_evidence | 9.6s |

### S14: 다중 제약 필터링

- 결과: **5/5** (평균 8.03s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 14.1 | 삼성전자(800만) + 김앤장(2,000만) = 2,800만 | hard | ANY | PASS | strongly_supported | 3.2s |
| 14.2 | Critical: SEC-001(완료), High: SEC-002,003,004(모두 완료) — 4개 섹션 동시 검색 필요 | extreme | ALL | PASS | strongly_supported | 25.0s |
| 14.3 | PAT-002만 PCT 완료 + 강지훈 발명 | hard | ANY | PASS | strongly_supported | 2.8s |
| 14.4 | 조직도: 백엔드(12명,박서연) + AI(15명,강지훈) | medium | ALL | PASS | strongly_supported | 5.9s |
| 14.5 | changelog: v2.4(7월, Adaptive Query Routing) + v2.5(10월, HyPE) | hard | ALL | PASS | strongly_supported | 3.4s |

### S15: 정량적 파생 계산

- 결과: **5/5** (평균 6.31s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 15.1 | 인프라: 6.5억/6명=1.08억 > AI: 12/15=0.8 > 백엔드: 8/12=0.67 | hard | ANY | PASS | strongly_supported | 3.4s |
| 15.2 | 김앤장2000+네이버1200+삼성800+KB600+현대600=5200/8267≈63% | extreme | ANY | PASS | strongly_supported | 3.8s |
| 15.3 | 52→152억 in 2년, CAGR=(152/52)^0.5-1≈71% | extreme | ANY | PASS | strongly_supported | 2.7s |
| 15.4 | 회의록: 인건비 5.8억(65%) + 인프라 0.5억(6%) = 6.3억(71%) | hard | ANY | PASS | strongly_supported | 3.2s |
| 15.5 | ARR 120억 / 32개사 = 3.75억. 또는 회의록: 평균 3,800만원/년 | medium | ANY | PASS | strongly_supported | 18.5s |

### S16: 교차 검증

- 결과: **3/4** (평균 5.49s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 16.1 | CEO: 실질 12~13개월, CFO: 10.7개월 — 시점/가정 차이 | hard | ALL | PASS | partially_supported | 6.2s |
| 16.2 | 회의록: 25명(개발15+영업5+기타5), 로드맵: 30명(개발15+영업5+기타10) | hard | ALL | **FAIL** | insufficient_evidence | 5.6s |
| 16.3 | 이메일5: 정식 출시 Q2 2025 = 로드맵 Q2 2025 QuantumGuard v1.0 | medium | ANY | PASS | partially_supported | 4.4s |
| 16.4 | 회의록: 약 20억원, 이메일6: 30억원 — 범위 차이 | hard | ALL | PASS | partially_supported | 5.7s |

<details><summary>실패 케이스 상세</summary>

**[16.2] 회의록: 25명(개발15+영업5+기타5), 로드맵: 30명(개발15+영업5+기타10)** (hard)
- 질문: 회의록의 채용 계획과 로드맵의 채용 계획이 일치하나요?
- 기대 키워드 (all): `['25', '30']`
- 실제 답변: 일치하지 않습니다.    - **회의록(2025년 사업 계획 의결 사항)**에는 **신규 채용 계획 25명 승인**(개발 15명, 영업 5명, 기타 5명)이 명시되어 있습니다. [2]   - **로드맵(QuantumRAG 2025 제품 로드맵)** 관련 컨텍스트에서는 **채용 계획(인원/부문)**이 확인되지 않습니다. 따라서 로드맵의 채용 계획과 회의록의 25명 계획을 **비교·검증할 근거가 부족**합니다. [16], [8], [7], [18], [25]  **결론:** 로드맵에 채용 계획이 제시되어 있지 않아 “일치 여부”를 판단

</details>

### S17: 다양한 문서 포맷 (PDF/HWPX)

- 결과: **16/20** (평균 11.43s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 17.1 | PDF: 저자/소속 기본 확인 | easy | ALL | PASS | strongly_supported | 4.9s |
| 17.2 | PDF: 아키텍처 핵심 개념 | medium | ANY | PASS | strongly_supported | 3.7s |
| 17.3 | PDF: COCO dataset 5000 image-caption pairs | medium | ANY | **FAIL** | insufficient_evidence | 32.3s |
| 17.4 | PDF: Image-Caption Similarity Assessment | easy | ANY | PASS | strongly_supported | 2.0s |
| 17.5 | PDF: Metrics for Generation Quality | medium | ALL | **FAIL** | insufficient_evidence | 18.3s |
| 17.6 | PDF: Methodology - triple extraction and alignment | hard | ANY | PASS | strongly_supported | 4.8s |
| 17.7 | PDF: Graph-based Contextual Consistency Comparison | medium | ANY | **FAIL** | insufficient_evidence | 93.8s |
| 17.8 | PDF: MKT assesses knowledge sufficiency, Alignment Test evaluates content alignment | hard | ANY | PASS | strongly_supported | 4.7s |
| 17.9 | PDF: Multi-Agent Collaboration via OVON | medium | ANY | PASS | strongly_supported | 3.2s |
| 17.10 | PDF: 3단계 리뷰 구조 | hard | ANY | **FAIL** | insufficient_evidence | 4.6s |
| 17.11 | HWPX: 기본 방향 | easy | ANY | PASS | strongly_supported | 8.8s |
| 17.12 | HWPX: 경제성장률 '25 1.8% | easy | ANY | PASS | strongly_supported | 2.8s |
| 17.13 | HWPX: 국가공무원 정원 약 4천 명 감축 | medium | ANY | PASS | strongly_supported | 2.8s |
| 17.14 | HWPX: 모바일 신분증 발급자 400만 명 돌파 | easy | ANY | PASS | strongly_supported | 2.7s |
| 17.15 | HWPX: 고향사랑기부제 '24잠정 879억 모금 | medium | ANY | PASS | strongly_supported | 2.4s |
| 17.16 | HWPX: '24 18개소→'25 35개소 | medium | ANY | PASS | strongly_supported | 17.3s |
| 17.17 | HWPX: 5개→19개 언어, '25.8. | medium | ALL | PASS | strongly_supported | 3.5s |
| 17.18 | HWPX: 드론‧SAR 활용 급경사지 붕괴위험 분석기술 | hard | ANY | PASS | strongly_supported | 5.7s |
| 17.19 | PDF+HWPX: 정보의 정확성과 신뢰성이라는 공통 주제 | extreme | ANY | PASS | partially_supported | 3.7s |
| 17.20 | PDF: Comprehensive Unlearning Techniques — 할루시네이션 최소화 | hard | ANY | PASS | strongly_supported | 6.6s |

<details><summary>실패 케이스 상세</summary>

**[17.3] PDF: COCO dataset 5000 image-caption pairs** (medium)
- 질문: ZeroH에서 할루시네이션 분석에 사용한 데이터셋과 규모는?
- 기대 키워드 (any): `['COCO', '5,000', '5000']`
- 실제 답변: 제공된 컨텍스트만으로는 **ZeroH에서 할루시네이션 분석에 사용한 데이터셋의 구체적 이름과 규모를 확인할 수 없습니다**. Source 1은 ZeroH Hallucination Framework 문서의 구성 섹션(Architecture, Features, Methodologies, Use Cases 등)만 요약하고 있을 뿐, 실제 데이터셋명이나 샘플 수/문서 수 같은 규모 정보는 포함하지 않습니다. [1]  따라서 질문에 대한 답은 **INSUFFICIENT_EVIDENCE**입니다. [1]  신뢰도: **INSUFFICIENT_

**[17.5] PDF: Metrics for Generation Quality** (medium)
- 질문: ZeroH의 생성 품질 평가 지표 3가지는 무엇인가요?
- 기대 키워드 (all): `['informativeness', 'consistency', 'fluency']`
- 실제 답변: INSUFFICIENT_EVIDENCE  제공된 컨텍스트에는 **ZeroH의 생성 품질 평가 지표 3가지**에 대한 정보가 없습니다. 관련된 평가 지표로는 퀀텀소프트의 **분기별 OKR 기반 평가**만 언급되어 있으며, ZeroH의 생성 품질 지표는 확인되지 않습니다.[1]  신뢰도: **INSUFFICIENT_EVIDENCE**

**[17.7] PDF: Graph-based Contextual Consistency Comparison** (medium)
- 질문: ZeroH에서 그래프 기반 문맥 일관성 비교에 사용하는 네트워크는?
- 기대 키워드 (any): `['RGCN', 'Relational Graph']`
- 실제 답변: INSUFFICIENT_EVIDENCE. 제공된 컨텍스트에는 ZeroH Hallucination Framework의 구성 섹션 목록만 있고, “그래프 기반 문맥 일관성 비교에 사용하는 네트워크”가 무엇인지에 대한 구체 내용은 없습니다. [1]

**[17.10] PDF: 3단계 리뷰 구조** (hard)
- 질문: ZeroH 프레임워크의 리뷰 레벨 구조는?
- 기대 키워드 (any): `['Front End Agent', 'Second Level Reviewer', 'Third Level Reviewer']`
- 실제 답변: 컨텍스트에 따르면 **ZeroH Hallucination Framework의 “리뷰(review) 레벨 구조”**(예: 몇 단계로 나뉜 리뷰 레벨, 각 레벨의 역할/구성 등)에 대한 구체적인 설명은 제공되어 있지 않습니다. 따라서 현재 자료만으로는 답변을 확정할 수 없습니다.    - INSUFFICIENT_EVIDENCE  **신뢰도 평가:** INSUFFICIENT_EVIDENCE

</details>

## 5. 체크리스트

- [x] 다종 문서 인제스트 (MD, TXT, CSV, PDF, DOCX, PPTX, XLSX, HWPX)
- [x] 단순 사실 확인 (S1)
- [ ] 멀티홉 추론 (S2)
- [x] 수치 계산/비교 (S3)
- [x] 시간/버전 추론 (S4)
- [x] 부정형/제외 (S5)
- [x] 교차 문서 종합 (S6)
- [x] 패러프레이즈/구어체 (S7)
- [ ] 멀티턴 엔티티 추적 (S8)
- [x] 엣지 케이스 (S9)
- [x] 정밀 검색 (S10)
- [ ] 암묵적 추론 (S11)
- [x] 경쟁사 비교 분석 (S12)
- [ ] 다양한 문서 포맷 (S17)
- [ ] 평균 응답 시간 < 5초
- [x] hard 난이도 통과율 > 60%

## 6. 성능 분석

| 구간 | 건수 | 비율 |
|------|------|------|
| < 2초 | 3건 | 3% |
| 2~4초 | 47건 | 44% |
| > 4초 | 57건 | 53% |

| 신뢰도 | 건수 |
|--------|------|
| insufficient_evidence | 15건 |
| partially_supported | 18건 |
| strongly_supported | 74건 |

## 7. 결론 및 개선 제안

전체 통과율 **90.7%**로 우수합니다.

### 개선이 필요한 영역

- **S2: 멀티홉 추론**: 4/6 — [2.2] 155억(기존) + 200억(Series C) = 355억, [2.5] 이메일: 2.5억 + 1.8억 + 3.2억 = 7.5억
- **S8: 멀티턴 대화 (엔티티 추적)**: 5/6 — [8.3] 문맥 유지: QuantumGuard 개발
- **S11: 암묵적 추론**: 3/5 — [11.3] 고객 사례: PoC 실패 시 Upstage 재전환 가능, [11.4] 특허 문서: 현재 정적 링크 사용 → 동적 링크 변경 필요
- **S16: 교차 검증**: 3/4 — [16.2] 회의록: 25명(개발15+영업5+기타5), 로드맵: 30명(개발15+영업5+기타10)
- **S17: 다양한 문서 포맷 (PDF/HWPX)**: 16/20 — [17.3] PDF: COCO dataset 5000 image-caption pairs, [17.5] PDF: Metrics for Generation Quality, [17.7] PDF: Graph-based Contextual Consistency Comparison, [17.10] PDF: 3단계 리뷰 구조

### 향후 혁신 방향

1. **LLM 기반 Query Decomposition**: 현재 규칙 기반 → LLM으로 자동 분해
2. **GraphRAG 통합**: 엔티티 관계 그래프로 멀티홉 추론 근본 해결
3. **Adaptive Chunk Size**: 문서 유형별 최적 청크 크기 자동 조정
4. **Cross-lingual Retrieval**: 한영 혼합 쿼리 임베딩 최적화
5. **Semantic Cache**: 유사 쿼리 캐싱으로 반복 질문 속도 10x 향상
