# QuantumRAG 시나리오 테스트 보고서 v2

> 실행일시: 2026-03-27 01:21:42
> 문서: 20개 | 청크: 217개 | 인제스트: 534.0s
> 혁신 기능: Contextual Chunk Enrichment, Query Decomposition, Entity Memory Tracker
> 테스트 구성: S1-S17 (baseline) + S18-S25 (advanced)

## 1. 요약 (Executive Summary)

| 항목 | 결과 |
|------|------|
| 전체 테스트 | 138건 |
| 통과 | 128건 |
| 실패 | 10건 |
| **통과율** | **92.8%** |
| 평균 응답 시간 | 4.48s |
| 최소/최대 응답 시간 | 0.00s / 16.39s |

### 버전 비교 (v1 Baseline vs v2 Advanced)

| 구분 | 테스트 수 | 통과 | 통과율 |
|------|----------|------|--------|
| S1-S17 (Baseline) | 138건 | 128건 | 92.8% |
| S18-S25 (Advanced) | 31건 | 28건 | 90.3% |
| **전체 (v2)** | **138건** | **128건** | **92.8%** |

### 난이도별 통과율

| 난이도 | 통과/전체 | 통과율 |
|--------|----------|--------|
| easy | 19/19 | 100% |
| medium | 41/45 | 91% |
| hard | 54/60 | 90% |
| extreme | 14/14 | 100% |

### 시나리오별 결과

| 시나리오 | 결과 | 통과율 | 평균 응답시간 |
|----------|------|--------|-------------|
| S1: 사실 확인 (기본) | 7/7 (PASS) | 100% | 2.45s |
| S2: 멀티홉 추론 | 5/6 (FAIL(1)) | 83% | 4.30s |
| S3: 수치 계산/비교 | 6/6 (PASS) | 100% | 3.25s |
| S4: 시간/버전 추론 | 6/6 (PASS) | 100% | 3.33s |
| S5: 부정형/제외 | 4/5 (FAIL(1)) | 80% | 11.70s |
| S6: 교차 문서 종합 | 5/5 (PASS) | 100% | 3.32s |
| S7: 패러프레이즈 | 6/6 (PASS) | 100% | 6.14s |
| S8: 멀티턴 대화 (엔티티 추적) | 6/6 (PASS) | 100% | 3.28s |
| S9: 엣지 케이스 | 7/7 (PASS) | 100% | 3.73s |
| S10: 정밀 검색 | 6/6 (PASS) | 100% | 2.67s |
| S11: 암묵적 추론 | 5/5 (PASS) | 100% | 5.11s |
| S12: 경쟁사 비교 | 2/3 (FAIL(1)) | 67% | 3.63s |
| S13: 조건부 추론 | 5/5 (PASS) | 100% | 4.11s |
| S14: 다중 제약 필터링 | 5/5 (PASS) | 100% | 3.92s |
| S15: 정량적 파생 계산 | 5/5 (PASS) | 100% | 3.99s |
| S16: 교차 검증 | 3/4 (FAIL(1)) | 75% | 5.35s |
| S17: 다양한 문서 포맷 (PDF/HWPX) | 17/20 (FAIL(3)) | 85% | 4.01s |
| S18: 불완전 정보 추론 | 5/5 (PASS) | 100% | 6.66s |
| S19: 모순/불일치 감지 | 4/4 (PASS) | 100% | 4.42s |
| S20: 한영 혼합 질의 | 3/4 (FAIL(1)) | 75% | 5.92s |
| S21: 반사실적 추론 | 4/4 (PASS) | 100% | 3.76s |
| S22: 수치 교차 검증 | 3/4 (FAIL(1)) | 75% | 6.69s |
| S23: 복합 조건부 질의 | 3/4 (FAIL(1)) | 75% | 6.07s |
| S24: 추상적/메타 질의 | 3/3 (PASS) | 100% | 4.48s |
| S25: 역방향 추론 | 3/3 (PASS) | 100% | 3.22s |

## 2. 인제스트 결과

| 항목 | 결과 |
|------|------|
| 문서 수 | 20개 |
| 청크 수 | 217개 |
| 소요 시간 | 534.0s |

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

- 결과: **7/7** (평균 2.45s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 1.1 | 기본 인물 조회 | easy | ANY | PASS | strongly_supported | 2.4s |
| 1.2 | 기본 수치 조회 | easy | ANY | PASS | strongly_supported | 2.6s |
| 1.3 | 계약서 수치 | easy | ANY | PASS | strongly_supported | 2.1s |
| 1.4 | 제품 버전 날짜 -- 청크 문맥 보강으로 해결 기대 | medium | ANY | PASS | strongly_supported | 3.5s |
| 1.5 | 조직도 수치 | easy | ANY | PASS | strongly_supported | 2.1s |
| 1.6 | 보안 감사 보고서 | easy | ANY | PASS | strongly_supported | 2.0s |
| 1.7 | 고객 사례 보고서 | easy | ANY | PASS | strongly_supported | 2.5s |

### S2: 멀티홉 추론

- 결과: **5/6** (평균 4.30s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 2.1 | 회의록+이메일: 45억 / 4.2억 | medium | ANY | PASS | strongly_supported | 2.8s |
| 2.2 | 155억(기존) + 200억(Series C) = 355억 | hard | ANY | PASS | strongly_supported | 7.1s |
| 2.3 | 조직도에서 박서연 겸임 + 예산 | medium | ALL | PASS | strongly_supported | 2.7s |
| 2.4 | 이메일(HyPE 성능 보고) + changelog 교차 | hard | ANY | PASS | strongly_supported | 4.1s |
| 2.5 | 이메일: 2.5억 + 1.8억 + 3.2억 = 7.5억 | hard | ANY | **FAIL** | strongly_supported | 5.5s |
| 2.6 | 이메일(ARR 180억 필요) + 이메일(하반기 신규 30억) | extreme | ANY | PASS | strongly_supported | 3.7s |

<details><summary>실패 케이스 상세</summary>

**[2.5] 이메일: 2.5억 + 1.8억 + 3.2억 = 7.5억** (hard)
- 질문: 일본 시장 PoC 3건의 총 예상 연 계약 규모는 얼마인가요?
- 기대 키워드 (any): `['7.5억', '7억5']`
- 실제 답변: 일본 시장 PoC 3건의 총 예상 연 계약 규모는 **연 5.7억원**입니다.   근거로, 미쓰비시 UFJ 은행 **연 2.5억원**과 NTT 데이터 **연 3.2억원**을 합하면 **총 연 5.7억원**입니다 [1]. 또한 별도 추출 정보로 NTT 데이터의 연 계약 규모가 **3.2억원**임이 확인됩니다 [2].  **답: 연 5.7억원 [1][2]**   **STRONGLY_SUPPORTED**

</details>

### S3: 수치 계산/비교

- 결과: **6/6** (평균 3.25s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 3.1 | (152-52)/52 = 192% | medium | ANY | PASS | strongly_supported | 2.4s |
| 3.2 | 회의록 비용 구조 | medium | ALL | PASS | strongly_supported | 2.2s |
| 3.3 | 조직도: 8+12+4+6.5+2 = 32.5억 | medium | ANY | PASS | strongly_supported | 6.1s |
| 3.4 | 이메일: 7.5/19.5 = 38.5% | hard | ANY | PASS | strongly_supported | 2.8s |
| 3.5 | 고객 사례: 주 8시간 -> 2.5시간 = 5.5시간 절감 | medium | ANY | PASS | strongly_supported | 2.6s |
| 3.6 | 감사 보고서: 심각1+높음3+중간2+낮음0 = 6~7건 조치 완료 / 13건 | hard | ANY | PASS | partially_supported | 3.4s |

### S4: 시간/버전 추론

- 결과: **6/6** (평균 3.33s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 4.1 | changelog breadcrumb으로 해결 기대 | medium | ANY | PASS | strongly_supported | 2.7s |
| 4.2 | v2.1 -> v2.3 변화 | hard | ANY | PASS | partially_supported | 5.5s |
| 4.3 | v2.4(라우팅, 2024-07) vs v2.5(HyPE, 2024-10) | medium | ANY | PASS | strongly_supported | 2.6s |
| 4.4 | changelog 호환성 섹션 | medium | ANY | PASS | strongly_supported | 2.7s |
| 4.5 | 이메일 + 로드맵 교차 | medium | ANY | PASS | strongly_supported | 2.2s |
| 4.6 | 로드맵 Q1 P0 항목 | medium | ALL | PASS | strongly_supported | 4.2s |

### S5: 부정형/제외

- 결과: **4/5** (평균 11.70s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 5.1 | 경쟁사 분석: 뤼튼만 X | medium | ANY | **FAIL** | partially_supported | 16.4s |
| 5.2 | 경쟁사 분석 표에서 X 찾기 | medium | ALL | PASS | strongly_supported | 15.4s |
| 5.3 | 보안 감사: 중간 5건 중 2건 완료, 3건 미조치 | hard | ANY | PASS | strongly_supported | 3.9s |
| 5.4 | HyPE는 v2.5.0에서 도입 | medium | ANY | PASS | strongly_supported | 16.3s |
| 5.5 | 특허: PAT-001은 한국만, PAT-002는 PCT 완료 | hard | ANY | PASS | insufficient_evidence | 6.6s |

<details><summary>실패 케이스 상세</summary>

**[5.1] 경쟁사 분석: 뤼튼만 X** (medium)
- 질문: 현재 온프레미스 배포를 지원하지 않는 경쟁사는 어디인가요?
- 기대 키워드 (any): `['뤼튼']`
- 실제 답변: 제공된 컨텍스트에서 **온프레미스 배포를 “지원하지 않는다(또는 미지원)”고 명시된 경쟁사는 퀀텀아이(QuantumSoft가 아닌 경쟁사)**입니다. [1]  - **퀀텀아이**: 온프레미스 **미지원**(“2025년 지원 예정”이 아니라, 경쟁사 항목에서 **온프레미스 배포 미지원**으로 기재) [1]   - 참고: 다른 경쟁사들은 온프레미스 관련 표기(✓ 또는 미정/예정)가 있어 “미지원”으로 단정할 근거가 컨텍스트에 없습니다. [2]  **출처** - [1] Source 1 (SWOT 약점: “온프레미스 배포 미지원 (2025

</details>

### S6: 교차 문서 종합

- 결과: **5/5** (평균 3.32s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 6.1 | 고객 사례: Enterprise, 82%, 스캔 PDF/이미지 | hard | ANY | PASS | strongly_supported | 3.4s |
| 6.2 | 이메일(속도 요구) + changelog(BM25 40% 개선) | hard | ANY | PASS | strongly_supported | 3.7s |
| 6.3 | 고객 사례: Upstage에서 전환, NDCG 개선 | hard | ANY | PASS | strongly_supported | 2.5s |
| 6.4 | 이메일(기능/가격) + 특허(PAT-004) | extreme | ANY | PASS | strongly_supported | 3.7s |
| 6.5 | 이메일(80억 R&D) + 로드맵(개발15+영업5+기타10=30명) | hard | ANY | PASS | partially_supported | 3.4s |

### S7: 패러프레이즈

- 결과: **6/6** (평균 6.14s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 7.1 | 보유 현금 45억 (일상적 표현) | easy | ANY | PASS | strongly_supported | 2.8s |
| 7.2 | 밸류에이션 (비공식 표현) | medium | ANY | PASS | strongly_supported | 2.9s |
| 7.3 | 보안 감사 Critical/High 항목 (구어체) | hard | ANY | PASS | strongly_supported | 5.4s |
| 7.4 | 이메일: NTT 데이터 3.2억 (최대 규모) | medium | ANY | PASS | strongly_supported | 7.1s |
| 7.5 | 특허 포트폴리오 (비격식 질문) | hard | ANY | PASS | partially_supported | 15.7s |
| 7.6 | 고객 사례: 최대 고객 | medium | ANY | PASS | strongly_supported | 3.1s |

### S8: 멀티턴 대화 (엔티티 추적)

- 결과: **6/6** (평균 3.28s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 8.1 | 직접 질문 | easy | ANY | PASS | strongly_supported | 2.9s |
| 8.2 | 대명사 resolve: 그 제품 -> QuantumGuard | medium | ANY | PASS | strongly_supported | 3.6s |
| 8.3 | 문맥 유지: QuantumGuard 개발 | medium | ANY | PASS | strongly_supported | 2.6s |
| 8.4 | 주제 전환 -- 경쟁사 분석 | medium | ANY | PASS | strongly_supported | 3.5s |
| 8.5 | 엔티티 추적: 그 회사 -> 퀀텀아이 | hard | ANY | PASS | strongly_supported | 3.8s |
| 8.6 | 주제 복귀 + 특허 교차 | hard | ANY | PASS | strongly_supported | 3.4s |

### S9: 엣지 케이스

- 결과: **7/7** (평균 3.73s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 9.1 | 빈 질문 | easy | ANY | PASS | insufficient_evidence | 0.0s |
| 9.2 | 문서에 없는 내용 | easy | ANY | PASS | insufficient_evidence | 5.3s |
| 9.3 | 공격적 어투 + 특수문자 | medium | ANY | PASS | strongly_supported | 4.8s |
| 9.4 | 반복 패턴이 포함된 긴 질문 | medium | ANY | PASS | strongly_supported | 2.0s |
| 9.5 | SQL injection 시도 | easy | ANY | PASS | partially_supported | 4.1s |
| 9.6 | 문서에 존재하지 않는 상세 정보 | easy | ANY | PASS | insufficient_evidence | 3.6s |
| 9.7 | 미래 예측 (문서에 없음) | easy | ANY | PASS | insufficient_evidence | 6.3s |

### S10: 정밀 검색

- 결과: **6/6** (평균 2.67s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 10.1 | 회의록/이메일 깊은 상세 정보 | medium | ALL | PASS | strongly_supported | 3.0s |
| 10.2 | changelog 특정 버전 상세 | medium | ALL | PASS | strongly_supported | 2.3s |
| 10.3 | 조직도 CSV의 특정 행 | easy | ALL | PASS | strongly_supported | 2.6s |
| 10.4 | 보안 감사 SEC-003 상세 | hard | ANY | PASS | strongly_supported | 2.9s |
| 10.5 | 이메일: HyPE 성능 표 | hard | ALL | PASS | strongly_supported | 2.8s |
| 10.6 | 특허 문서 상세 | hard | ALL | PASS | strongly_supported | 2.5s |

### S11: 암묵적 추론

- 결과: **5/5** (평균 5.11s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 11.1 | 특허: PAT-001, 002, 003, 004에 모두 등재 -> 강지훈 4건 | hard | ANY | PASS | strongly_supported | 5.3s |
| 11.2 | 이메일: 3.8억->4.2억 = 0.4억 증가 | hard | ANY | PASS | insufficient_evidence | 9.9s |
| 11.3 | 고객 사례: PoC 실패 시 Upstage 재전환 가능 | hard | ANY | PASS | strongly_supported | 2.1s |
| 11.4 | 특허 문서: 현재 정적 링크 사용 -> 동적 링크 변경 필요 | hard | ANY | PASS | strongly_supported | 3.1s |
| 11.5 | 특허: AGPL 네트워크 사용 조항 | hard | ANY | PASS | strongly_supported | 5.1s |

### S12: 경쟁사 비교

- 결과: **2/3** (평균 3.63s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 12.1 | 특허: 퀀텀소프트 3건 vs 퀀텀아이 8, 리턴제로 12, 42Maru 5 | hard | ANY | **FAIL** | insufficient_evidence | 1.6s |
| 12.2 | 고객 사례(월 1,200만 계약) + 경쟁사(점유율) | extreme | ANY | PASS | partially_supported | 3.1s |
| 12.3 | 이메일(NTT 경쟁) + 경쟁사 분석(기술 비교) | extreme | ANY | PASS | partially_supported | 6.2s |

<details><summary>실패 케이스 상세</summary>

**[12.1] 특허: 퀀텀소프트 3건 vs 퀀텀아이 8, 리턴제로 12, 42Maru 5** (hard)
- 질문: 특허 건수 기준으로 퀀텀소프트보다 많은 특허를 보유한 경쟁사는?
- 기대 키워드 (any): `['퀀텀아이', '리턴제로', '42Maru', '포티투마루']`
- 실제 답변: Generation failed: [openai] Provider error: Error code: 400 - {'error': {'message': "We could not parse the JSON body of your request. (HINT: This likely means you aren't using your HTTP library correctly. The OpenAI API expects a JSON payload, but what was sent was not valid JSON. If you have troub

</details>

### S13: 조건부 추론

- 결과: **5/5** (평균 4.11s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 13.1 | 이메일6: R&D 인력 80억 > 운영 50억 > QuantumGuard 40억 > 일본 30억 | medium | ANY | PASS | strongly_supported | 2.2s |
| 13.2 | 런웨이 10.7개월, Q2 2025까지 약 7-8개월 -> 가능하지만 여유 없음 | hard | ANY | PASS | insufficient_evidence | 7.5s |
| 13.3 | 고객 사례(스캔 PDF 요청) + 로드맵(Q1 OCR 통합) | hard | ANY | PASS | strongly_supported | 2.8s |
| 13.4 | 회의록: 월 2,400만 -> 월 1,500만 절감 (60%), 연 1.8억 | hard | ANY | PASS | strongly_supported | 2.4s |
| 13.5 | 현재 ARR 120억 -> 180억 필요 = +60억. 파이프라인 19.5억(이메일) + 28억(회의록) | extreme | ANY | PASS | partially_supported | 5.6s |

### S14: 다중 제약 필터링

- 결과: **5/5** (평균 3.92s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 14.1 | 삼성전자(800만) + 김앤장(2,000만) = 2,800만 | hard | ANY | PASS | partially_supported | 3.6s |
| 14.2 | Critical: SEC-001(완료), High: SEC-002,003,004(모두 완료) -- 4개 섹션 동시 검색 필요 | extreme | ALL | PASS | strongly_supported | 2.8s |
| 14.3 | PAT-002만 PCT 완료 + 강지훈 발명 | hard | ANY | PASS | strongly_supported | 3.3s |
| 14.4 | 조직도: 백엔드(12명,박서연) + AI(15명,강지훈) | medium | ALL | PASS | strongly_supported | 2.9s |
| 14.5 | changelog: v2.4(7월, Adaptive Query Routing) + v2.5(10월, HyPE) | hard | ALL | PASS | strongly_supported | 7.1s |

### S15: 정량적 파생 계산

- 결과: **5/5** (평균 3.99s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 15.1 | 인프라: 6.5억/6명=1.08억 > AI: 12/15=0.8 > 백엔드: 8/12=0.67 | hard | ANY | PASS | strongly_supported | 4.2s |
| 15.2 | 김앤장2000+네이버1200+삼성800+KB600+현대600=5200/8267=63% | extreme | ANY | PASS | strongly_supported | 5.6s |
| 15.3 | 52->152억 in 2년, CAGR=(152/52)^0.5-1=71% | extreme | ANY | PASS | strongly_supported | 3.4s |
| 15.4 | 회의록: 인건비 5.8억(65%) + 인프라 0.5억(6%) = 6.3억(71%) | hard | ANY | PASS | strongly_supported | 4.0s |
| 15.5 | ARR 120억 / 32개사 = 3.75억. 또는 회의록: 평균 3,800만원/년 | medium | ANY | PASS | partially_supported | 2.9s |

### S16: 교차 검증

- 결과: **3/4** (평균 5.35s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 16.1 | CEO: 실질 12~13개월, CFO: 10.7개월 -- 시점/가정 차이 | hard | ALL | PASS | strongly_supported | 5.8s |
| 16.2 | 회의록: 25명(개발15+영업5+기타5), 로드맵: 30명(개발15+영업5+기타10) | hard | ALL | PASS | strongly_supported | 7.6s |
| 16.3 | 이메일5: 정식 출시 Q2 2025 = 로드맵 Q2 2025 QuantumGuard v1.0 | medium | ANY | PASS | partially_supported | 4.0s |
| 16.4 | 회의록: 약 20억원, 이메일6: 30억원 -- 범위 차이 | hard | ALL | **FAIL** | partially_supported | 4.0s |

<details><summary>실패 케이스 상세</summary>

**[16.4] 회의록: 약 20억원, 이메일6: 30억원 -- 범위 차이** (hard)
- 질문: 일본 법인 설립 비용이 이메일과 회의록에서 다른데, 각각 얼마인가요?
- 기대 키워드 (all): `['20억', '30억']`
- 실제 답변: 일본 법인 설립 비용은 **이메일과 회의록에서 서로 다르게** 제시되어 있습니다.  - **회의록(2024년 4분기 경영진 회의록, 일본 시장 안건)**: 일본 법인 설립 + 현지 인력 3명에 대한 **투자 소요 약 20억원**으로 기재되어 있습니다. [1]   - **이메일(2024-09-15 CEO 메일)**: 일본 법인 설립 비용의 **별도 금액이 명시되어 있지 않고**, “일본 법인 설립 비용을 감안”했다는 문장만 있습니다. [2]  따라서, 이메일 기준으로는 “일본 법인 설립 비용”의 **정확한 금액을 확인할 수 없습니다(

</details>

### S17: 다양한 문서 포맷 (PDF/HWPX)

- 결과: **17/20** (평균 4.01s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 17.1 | PDF: 저자/소속 기본 확인 | easy | ALL | PASS | strongly_supported | 3.8s |
| 17.2 | PDF: 아키텍처 핵심 개념 | medium | ANY | PASS | strongly_supported | 3.5s |
| 17.3 | PDF: COCO dataset 5000 image-caption pairs | medium | ANY | PASS | strongly_supported | 2.3s |
| 17.4 | PDF: Image-Caption Similarity Assessment | easy | ANY | PASS | strongly_supported | 2.9s |
| 17.5 | PDF: Metrics for Generation Quality | medium | ALL | PASS | strongly_supported | 4.4s |
| 17.6 | PDF: Methodology - triple extraction and alignment | hard | ANY | PASS | strongly_supported | 4.7s |
| 17.7 | PDF: Graph-based Contextual Consistency Comparison | medium | ANY | **FAIL** | insufficient_evidence | 4.9s |
| 17.8 | PDF: MKT assesses knowledge sufficiency, Alignment Test evaluates content alignment | hard | ANY | PASS | insufficient_evidence | 5.0s |
| 17.9 | PDF: Multi-Agent Collaboration via OVON | medium | ANY | **FAIL** | insufficient_evidence | 4.6s |
| 17.10 | PDF: 3단계 리뷰 구조 | hard | ANY | **FAIL** | insufficient_evidence | 5.5s |
| 17.11 | HWPX: 기본 방향 | easy | ANY | PASS | strongly_supported | 2.3s |
| 17.12 | HWPX: 경제성장률 '25 1.8% | easy | ANY | PASS | strongly_supported | 6.3s |
| 17.13 | HWPX: 국가공무원 정원 약 4천 명 감축 | medium | ANY | PASS | strongly_supported | 2.3s |
| 17.14 | HWPX: 모바일 신분증 발급자 400만 명 돌파 | easy | ANY | PASS | strongly_supported | 3.9s |
| 17.15 | HWPX: 고향사랑기부제 '24잠정 879억 모금 | medium | ANY | PASS | strongly_supported | 5.8s |
| 17.16 | HWPX: '24 18개소->'25 35개소 | medium | ANY | PASS | strongly_supported | 2.2s |
| 17.17 | HWPX: 5개->19개 언어, '25.8. | medium | ALL | PASS | strongly_supported | 2.2s |
| 17.18 | HWPX: 드론/SAR 활용 급경사지 붕괴위험 분석기술 | hard | ANY | PASS | strongly_supported | 2.4s |
| 17.19 | PDF+HWPX: 정보의 정확성과 신뢰성이라는 공통 주제 | extreme | ANY | PASS | partially_supported | 7.0s |
| 17.20 | PDF: Comprehensive Unlearning Techniques -- 할루시네이션 최소화 | hard | ANY | PASS | strongly_supported | 4.0s |

<details><summary>실패 케이스 상세</summary>

**[17.7] PDF: Graph-based Contextual Consistency Comparison** (medium)
- 질문: ZeroH에서 그래프 기반 문맥 일관성 비교에 사용하는 네트워크는?
- 기대 키워드 (any): `['RGCN', 'Relational Graph']`
- 실제 답변: 제공된 컨텍스트만으로는 **ZeroH에서 그래프 기반 문맥 일관성 비교에 사용하는 네트워크가 무엇인지 명시적으로 확인할 수 없습니다**. ZeroH 관련 내용은 hallucination 유형, 완화 전략, unlearning 과정, OVON 상호운용 표준, Conversation Envelopes, 다중 에이전트 리뷰 구조 등을 설명하지만, 질문하신 **“그래프 기반 문맥 일관성 비교에 사용하는 네트워크”**의 구체 명칭은 나오지 않습니다. [2][19]  신뢰도: **INSUFFICIENT_EVIDENCE**

**[17.9] PDF: Multi-Agent Collaboration via OVON** (medium)
- 질문: ZeroH에서 에이전트 간 통신에 사용하는 표준 프레임워크는?
- 기대 키워드 (any): `['OVON', 'Open Voice Network']`
- 실제 답변: 컨텍스트에 **ZeroH Hallucination Framework에서 에이전트 간 통신에 사용하는 “표준 프레임워크”**가 무엇인지에 대한 정보가 없습니다. ZeroH는 *multi-agent orchestration*을 사용한다고만 설명되어 있으며, 에이전트 간 통신을 위한 특정 표준 프레임워크(예: 메시징/오케스트레이션 프레임워크 이름)는 언급되지 않습니다. [12]  **따라서 답변: 컨텍스트만으로는 확인 불가(INSUFFICIENT_EVIDENCE).**  - **신뢰도: INSUFFICIENT_EVIDENCE**

**[17.10] PDF: 3단계 리뷰 구조** (hard)
- 질문: ZeroH 프레임워크의 리뷰 레벨 구조는?
- 기대 키워드 (any): `['Front End Agent', 'Second Level Reviewer', 'Third Level Reviewer']`
- 실제 답변: 제공된 컨텍스트에는 **“ZeroH 프레임워크의 리뷰 레벨 구조(예: 레벨 1/2/3 같은 계층 구조)”**가 구체적으로 제시되어 있지 않습니다. [1][3] 또한 컨텍스트의 “Features/Methodologies” 섹션은 구성 요소(예: multi-agent orchestration, contextual consistency evaluation, response segmentation 등)를 설명하지만, **리뷰를 어떤 레벨로 나누는지에 대한 명시적 구조**는 확인되지 않습니다. [3]  따라서 질문에 대해 **컨텍스트만으로는

</details>

### S18: 불완전 정보 추론

- 결과: **5/5** (평균 6.66s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 18.1 | 문서에 총 인원/예산은 있으나 1인당 연봉은 없음 -- 부분 정보 인정 필요 | hard | ANY | PASS | insufficient_evidence | 9.8s |
| 18.2 | 조직도에 이름만 있고 성별 정보 없음 | medium | ANY | PASS | insufficient_evidence | 5.4s |
| 18.3 | 학술 논문이므로 실제 배포 사례 없음 | medium | ANY | PASS | insufficient_evidence | 4.6s |
| 18.4 | HWPX에 개별 프로그램 예산은 있으나 총액 합산은 불명확 | hard | ANY | PASS | insufficient_evidence | 4.1s |
| 18.5 | 직접 명시되지 않음 -- 감사 결과에서 간접 추론 가능하나 수치 불가 | hard | ANY | PASS | insufficient_evidence | 9.4s |

### S19: 모순/불일치 감지

- 결과: **4/4** (평균 4.42s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 19.1 | 회의록/이메일 간 날짜 교차 확인 | hard | ALL | PASS | strongly_supported | 2.7s |
| 19.2 | 전체 등급 vs 개별 항목 정합성 검증 | extreme | ANY | PASS | strongly_supported | 3.2s |
| 19.3 | 시간적 일관성 확인 | hard | ANY | PASS | partially_supported | 5.9s |
| 19.4 | CEO 12-13개월 vs CFO 10.7개월 | hard | ANY | PASS | partially_supported | 5.9s |

### S20: 한영 혼합 질의

- 결과: **3/4** (평균 5.92s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 20.1 | 한영 혼합: 기술 용어(영) + 질문(한) | medium | ANY | **FAIL** | insufficient_evidence | 8.4s |
| 20.2 | PDF 기반 영어 기술 용어 + 한국어 문맥 | hard | ANY | PASS | insufficient_evidence | 5.3s |
| 20.3 | 영어 비즈니스 용어 + 한국어 데이터 | medium | ANY | PASS | strongly_supported | 3.7s |
| 20.4 | 기술 용어 혼합 -- 문서에 직접 정보 부족할 수 있음 | hard | ANY | PASS | insufficient_evidence | 6.3s |

<details><summary>실패 케이스 상세</summary>

**[20.1] 한영 혼합: 기술 용어(영) + 질문(한)** (medium)
- 질문: QuantumRAG의 Triple Index Fusion에서 BM25 weight는 기본값이 얼마인가요?
- 기대 키워드 (any): `['0.25', '25%']`
- 실제 답변: 제공된 컨텍스트에는 **Triple Index Fusion에서 BM25 weight(가중치) 기본값**이 얼마인지에 대한 수치가 없습니다. 따라서 기본값을 특정해 답변할 수 없습니다. [11], [15]  - Triple Index Fusion이 “임베딩 + HyPE + BM25”를 결합한다는 점은 확인됩니다. [11], [15] - 하지만 **BM25 weight의 기본값(예: 0.xx)**은 컨텍스트에 명시되어 있지 않습니다. [11], [15]  **신뢰도: INSUFFICIENT_EVIDENCE**

</details>

### S21: 반사실적 추론

- 결과: **4/4** (평균 3.76s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 21.1 | 런웨이 10.7개월 기반 가정 추론 | hard | ANY | PASS | strongly_supported | 3.0s |
| 21.2 | 현재 ARR 120억 + 일본 7.5억 = 127.5억 | extreme | ANY | PASS | strongly_supported | 3.8s |
| 21.3 | HyPE 도입 전 성능 수준으로 회귀 가정 | hard | ANY | PASS | strongly_supported | 4.3s |
| 21.4 | HWPX: 디지털 플랫폼 연관 사업 식별 | hard | ANY | PASS | partially_supported | 4.0s |

### S22: 수치 교차 검증

- 결과: **3/4** (평균 6.69s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 22.1 | 고객 사례 보고서에 명시된 개별 고객 수 vs 전체 32개 | extreme | ANY | PASS | strongly_supported | 12.3s |
| 22.2 | 특허 문서의 날짜 기반 정렬 및 간격 계산 | hard | ANY | PASS | strongly_supported | 3.1s |
| 22.3 | 조직도 CSV 합산 vs 회사 소개 수치 비교 | medium | ANY | PASS | strongly_supported | 5.5s |
| 22.4 | changelog에서 하반기 항목 분류 및 집계 | hard | ALL | **FAIL** | strongly_supported | 5.8s |

<details><summary>실패 케이스 상세</summary>

**[22.4] changelog에서 하반기 항목 분류 및 집계** (hard)
- 질문: 2024년 하반기 changelog의 기능 추가 건수와 버그 수정 건수를 각각 알려주세요
- 기대 키워드 (all): `['v2.4', 'v2.5']`
- 실제 답변: 2024년 하반기 changelog 기준으로 **기능 추가는 8건**, **버그 수정은 2건**입니다.   - 기능 추가: 2건 + 3건 + 3건 = **8건** [4][21][25]   - 버그 수정: 2건 + 0건 + 0건 = **2건** [4][21][25]  **STRONGLY_SUPPORTED**

</details>

### S23: 복합 조건부 질의

- 결과: **3/4** (평균 6.07s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 23.1 | 다중 조건: 배포 방식 + 등급 + 만족도 필터링 | extreme | ANY | PASS | insufficient_evidence | 7.4s |
| 23.2 | 보안 감사: 등급 + 조치 상태 교차 필터 | hard | ANY | PASS | strongly_supported | 6.4s |
| 23.3 | 시간 구간별 마일스톤 분류 | hard | ANY | **FAIL** | strongly_supported | 4.0s |
| 23.4 | 매출 + 만족도 이중 조건 필터 | hard | ANY | PASS | strongly_supported | 6.5s |

<details><summary>실패 케이스 상세</summary>

**[23.3] 시간 구간별 마일스톤 분류** (hard)
- 질문: 2024년 Q4에 달성한 마일스톤과 2025 Q1에 계획된 마일스톤을 각각 알려주세요
- 기대 키워드 (any): `['QuantumGuard', '프로토타입', 'v3.0', 'Atlas']`
- 실제 답변: 2024년 Q4에 **달성한 마일스톤**은 추출된 정보에 **명시되어 있지 않습니다**.  2025년 Q1에 **계획된 마일스톤**은 다음과 같습니다: - **데이터베이스 마이그레이션**: PostgreSQL 14 → 16 [42]  STRONGLY_SUPPORTED

</details>

### S24: 추상적/메타 질의

- 결과: **3/3** (평균 4.48s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 24.1 | 여러 문서에서 리스크 요인 추출 및 우선순위 판단 | extreme | ANY | PASS | partially_supported | 4.7s |
| 24.2 | PDF 전체 요약 -- 학술적 기여 추출 | hard | ANY | PASS | strongly_supported | 3.7s |
| 24.3 | HWPX에서 디지털 전환 관련 항목 필터링 | hard | ANY | PASS | strongly_supported | 5.1s |

### S25: 역방향 추론

- 결과: **3/3** (평균 3.22s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 25.1 | 수치에서 역방향으로 원인 추적 | hard | ANY | PASS | partially_supported | 3.0s |
| 25.2 | 수치 -> 문맥 역추적 | medium | ANY | PASS | strongly_supported | 3.3s |
| 25.3 | HWPX: 고향사랑기부제 모금액 역추적 | medium | ANY | PASS | strongly_supported | 3.3s |

## 5. v2 고급 시나리오 분석

### 시나리오 카테고리별 분석

- **S18: 불완전 정보 추론**: 5/5 (100%)
  - 불완전 정보 추론 -- 정보 부족 시 적절한 응답 능력
- **S19: 모순/불일치 감지**: 4/4 (100%)
  - 모순/불일치 감지 -- 문서 간 데이터 정합성 검증 능력
- **S20: 한영 혼합 질의**: 3/4 (75%)
  - 한영 혼합 질의 -- 이중 언어 기술 용어 처리 능력
- **S21: 반사실적 추론**: 4/4 (100%)
  - 반사실적 추론 -- 가정 기반 논리적 추론 능력
- **S22: 수치 교차 검증**: 3/4 (75%)
  - 세밀한 수치 교차 검증 -- 수치 데이터 일관성 검증 능력
- **S23: 복합 조건부 질의**: 3/4 (75%)
  - 복합 조건부 질의 -- 다중 필터 조합 처리 능력
- **S24: 추상적/메타 질의**: 3/3 (100%)
  - 추상적/메타 질의 -- 상위 수준 분석 및 요약 능력
- **S25: 역방향 추론**: 3/3 (100%)
  - 역방향 추론 -- 결과에서 원인으로의 역추적 능력

## 6. 체크리스트

- [x] 다종 문서 인제스트 (MD, TXT, CSV, PDF, DOCX, PPTX, XLSX, HWPX)
- [x] 단순 사실 확인 (S1)
- [ ] 멀티홉 추론 (S2)
- [x] 수치 계산/비교 (S3)
- [x] 시간/버전 추론 (S4)
- [ ] 부정형/제외 (S5)
- [x] 교차 문서 종합 (S6)
- [x] 패러프레이즈/구어체 (S7)
- [x] 멀티턴 엔티티 추적 (S8)
- [x] 엣지 케이스 (S9)
- [x] 정밀 검색 (S10)
- [x] 암묵적 추론 (S11)
- [ ] 경쟁사 비교 분석 (S12)
- [ ] 다양한 문서 포맷 (S17)
- [x] 불완전 정보 추론 (S18)
- [x] 모순/불일치 감지 (S19)
- [ ] 한영 혼합 질의 (S20)
- [x] 반사실적 추론 (S21)
- [ ] 수치 교차 검증 (S22)
- [ ] 복합 조건부 질의 (S23)
- [x] 추상적/메타 질의 (S24)
- [x] 역방향 추론 (S25)
- [x] 평균 응답 시간 < 5초
- [x] hard 난이도 통과율 > 60%
- [x] extreme 난이도 통과율 > 40%

## 7. 성능 분석

| 구간 | 건수 | 비율 |
|------|------|------|
| < 2초 | 3건 | 2% |
| 2~4초 | 78건 | 57% |
| > 4초 | 57건 | 41% |

| 신뢰도 | 건수 |
|--------|------|
| insufficient_evidence | 21건 |
| partially_supported | 19건 |
| strongly_supported | 98건 |

## 8. 결론 및 개선 제안

전체 통과율 **92.8%**로 우수합니다.

### Baseline vs Advanced 비교 인사이트

- Baseline(93%)과 Advanced(90%) 통과율이 유사합니다.
- 고급 추론 능력이 기본 능력과 균형을 이루고 있습니다.

### 개선이 필요한 영역

- **S2: 멀티홉 추론**: 5/6 -- [2.5] 이메일: 2.5억 + 1.8억 + 3.2억 = 7.5억
- **S5: 부정형/제외**: 4/5 -- [5.1] 경쟁사 분석: 뤼튼만 X
- **S12: 경쟁사 비교**: 2/3 -- [12.1] 특허: 퀀텀소프트 3건 vs 퀀텀아이 8, 리턴제로 12, 42Maru 5
- **S16: 교차 검증**: 3/4 -- [16.4] 회의록: 약 20억원, 이메일6: 30억원 -- 범위 차이
- **S17: 다양한 문서 포맷 (PDF/HWPX)**: 17/20 -- [17.7] PDF: Graph-based Contextual Consistency Comparison, [17.9] PDF: Multi-Agent Collaboration via OVON, [17.10] PDF: 3단계 리뷰 구조
- **S20: 한영 혼합 질의**: 3/4 -- [20.1] 한영 혼합: 기술 용어(영) + 질문(한)
- **S22: 수치 교차 검증**: 3/4 -- [22.4] changelog에서 하반기 항목 분류 및 집계
- **S23: 복합 조건부 질의**: 3/4 -- [23.3] 시간 구간별 마일스톤 분류

### 향후 혁신 방향

1. **LLM 기반 Query Decomposition**: 현재 규칙 기반 -> LLM으로 자동 분해
2. **GraphRAG 통합**: 엔티티 관계 그래프로 멀티홉 추론 근본 해결
3. **Adaptive Chunk Size**: 문서 유형별 최적 청크 크기 자동 조정
4. **Cross-lingual Retrieval**: 한영 혼합 쿼리 임베딩 최적화
5. **Semantic Cache**: 유사 쿼리 캐싱으로 반복 질문 속도 10x 향상
6. **Contradiction-aware Generation**: 모순 감지 후 명시적 불일치 보고
7. **Confidence Calibration**: 불완전 정보에 대한 신뢰도 보정 강화
8. **Counterfactual Reasoning Chain**: 가정 기반 추론 체인 구조화
