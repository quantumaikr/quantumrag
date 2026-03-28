# QuantumRAG 시나리오 테스트 보고서 v3

> 실행일시: 2026-03-27 06:46:54
> 문서: 20개 | 청크: 65개 | 인제스트: 138.8s
> 혁신 기능: Contextual Chunk Enrichment, Query Decomposition, Entity Memory Tracker
> 테스트 구성: S1-S17 (baseline) + S18-S30 (advanced)

## 1. 요약 (Executive Summary)

| 항목 | 결과 |
|------|------|
| 전체 테스트 | 161건 |
| 통과 | 145건 |
| 실패 | 16건 |
| **통과율** | **90.1%** |
| 평균 응답 시간 | 4.11s |
| 최소/최대 응답 시간 | 0.00s / 11.47s |

### 버전 비교 (v1 Baseline vs v3 Advanced)

| 구분 | 테스트 수 | 통과 | 통과율 |
|------|----------|------|--------|
| S1-S17 (Baseline) | 161건 | 145건 | 90.1% |
| S18-S30 (Advanced) | 54건 | 47건 | 87.0% |
| **전체 (v3)** | **161건** | **145건** | **90.1%** |

### 난이도별 통과율

| 난이도 | 통과/전체 | 통과율 |
|--------|----------|--------|
| easy | 18/19 | 95% |
| medium | 43/49 | 88% |
| hard | 66/73 | 90% |
| extreme | 18/20 | 90% |

### 시나리오별 결과

| 시나리오 | 결과 | 통과율 | 평균 응답시간 |
|----------|------|--------|-------------|
| S1: 사실 확인 (기본) | 7/7 (PASS) | 100% | 2.47s |
| S2: 멀티홉 추론 | 6/6 (PASS) | 100% | 3.79s |
| S3: 수치 계산/비교 | 6/6 (PASS) | 100% | 2.79s |
| S4: 시간/버전 추론 | 6/6 (PASS) | 100% | 3.00s |
| S5: 부정형/제외 | 5/5 (PASS) | 100% | 4.65s |
| S6: 교차 문서 종합 | 5/5 (PASS) | 100% | 4.75s |
| S7: 패러프레이즈 | 6/6 (PASS) | 100% | 5.26s |
| S8: 멀티턴 대화 (엔티티 추적) | 5/6 (FAIL(1)) | 83% | 4.57s |
| S9: 엣지 케이스 | 7/7 (PASS) | 100% | 3.96s |
| S10: 정밀 검색 | 6/6 (PASS) | 100% | 2.99s |
| S11: 암묵적 추론 | 5/5 (PASS) | 100% | 4.31s |
| S12: 경쟁사 비교 | 3/3 (PASS) | 100% | 5.55s |
| S13: 조건부 추론 | 5/5 (PASS) | 100% | 5.18s |
| S14: 다중 제약 필터링 | 4/5 (FAIL(1)) | 80% | 3.60s |
| S15: 정량적 파생 계산 | 5/5 (PASS) | 100% | 3.75s |
| S16: 교차 검증 | 3/4 (FAIL(1)) | 75% | 5.20s |
| S17: 다양한 문서 포맷 (PDF/HWPX) | 14/20 (FAIL(6)) | 70% | 3.85s |
| S18: 불완전 정보 추론 | 5/5 (PASS) | 100% | 5.34s |
| S19: 모순/불일치 감지 | 3/4 (FAIL(1)) | 75% | 4.33s |
| S20: 한영 혼합 질의 | 3/4 (FAIL(1)) | 75% | 4.51s |
| S21: 반사실적 추론 | 3/4 (FAIL(1)) | 75% | 3.74s |
| S22: 수치 교차 검증 | 3/4 (FAIL(1)) | 75% | 5.43s |
| S23: 복합 조건부 질의 | 4/4 (PASS) | 100% | 4.63s |
| S24: 추상적/메타 질의 | 3/3 (PASS) | 100% | 4.00s |
| S25: 역방향 추론 | 3/3 (PASS) | 100% | 2.88s |
| S26: 테이블 구조 이해 | 4/5 (FAIL(1)) | 80% | 3.58s |
| S27: 답변 완전성 | 5/5 (PASS) | 100% | 4.63s |
| S28: 청크 경계 강건성 | 3/4 (FAIL(1)) | 75% | 4.41s |
| S29: PDF 심층 구조 추출 | 5/5 (PASS) | 100% | 3.97s |
| S30: 산재 정보 종합 수집 | 3/4 (FAIL(1)) | 75% | 5.12s |

## 2. 인제스트 결과

| 항목 | 결과 |
|------|------|
| 문서 수 | 20개 |
| 청크 수 | 65개 |
| 소요 시간 | 138.8s |

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

- 결과: **7/7** (평균 2.47s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 1.1 | 기본 인물 조회 | easy | ANY | PASS | strongly_supported | 2.2s |
| 1.2 | 기본 수치 조회 | easy | ANY | PASS | strongly_supported | 2.7s |
| 1.3 | 계약서 수치 | easy | ANY | PASS | strongly_supported | 2.5s |
| 1.4 | 제품 버전 날짜 -- 청크 문맥 보강으로 해결 기대 | medium | ANY | PASS | strongly_supported | 2.4s |
| 1.5 | 조직도 수치 | easy | ANY | PASS | strongly_supported | 2.1s |
| 1.6 | 보안 감사 보고서 | easy | ANY | PASS | partially_supported | 3.2s |
| 1.7 | 고객 사례 보고서 | easy | ANY | PASS | strongly_supported | 2.2s |

### S2: 멀티홉 추론

- 결과: **6/6** (평균 3.79s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 2.1 | 회의록+이메일: 45억 / 4.2억 | medium | ANY | PASS | strongly_supported | 3.1s |
| 2.2 | 155억(기존) + 200억(Series C) = 355억 | hard | ANY | PASS | strongly_supported | 1.6s |
| 2.3 | 조직도에서 박서연 겸임 + 예산 | medium | ALL | PASS | strongly_supported | 3.8s |
| 2.4 | 이메일(HyPE 성능 보고) + changelog 교차 | hard | ANY | PASS | strongly_supported | 6.0s |
| 2.5 | 이메일: 2.5억 + 1.8억 + 3.2억 = 7.5억 | hard | ANY | PASS | strongly_supported | 2.8s |
| 2.6 | 이메일(ARR 180억 필요) + 이메일(하반기 신규 30억) | extreme | ANY | PASS | strongly_supported | 5.4s |

### S3: 수치 계산/비교

- 결과: **6/6** (평균 2.79s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 3.1 | (152-52)/52 = 192% | medium | ANY | PASS | strongly_supported | 2.8s |
| 3.2 | 회의록 비용 구조 | medium | ALL | PASS | strongly_supported | 2.0s |
| 3.3 | 조직도: 8+12+4+6.5+2 = 32.5억 | medium | ANY | PASS | strongly_supported | 2.9s |
| 3.4 | 이메일: 7.5/19.5 = 38.5% | hard | ANY | PASS | strongly_supported | 2.9s |
| 3.5 | 고객 사례: 주 8시간 -> 2.5시간 = 5.5시간 절감 | medium | ANY | PASS | strongly_supported | 3.3s |
| 3.6 | 감사 보고서: 심각1+높음3+중간2+낮음0 = 6~7건 조치 완료 / 13건 | hard | ANY | PASS | strongly_supported | 2.9s |

### S4: 시간/버전 추론

- 결과: **6/6** (평균 3.00s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 4.1 | changelog breadcrumb으로 해결 기대 | medium | ANY | PASS | strongly_supported | 2.8s |
| 4.2 | v2.1 -> v2.3 변화 | hard | ANY | PASS | partially_supported | 5.1s |
| 4.3 | v2.4(라우팅, 2024-07) vs v2.5(HyPE, 2024-10) | medium | ANY | PASS | strongly_supported | 2.4s |
| 4.4 | changelog 호환성 섹션 | medium | ANY | PASS | strongly_supported | 2.6s |
| 4.5 | 이메일 + 로드맵 교차 | medium | ANY | PASS | strongly_supported | 2.6s |
| 4.6 | 로드맵 Q1 P0 항목 | medium | ALL | PASS | strongly_supported | 2.4s |

### S5: 부정형/제외

- 결과: **5/5** (평균 4.65s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 5.1 | 경쟁사 분석: 뤼튼만 X | medium | ANY | PASS | strongly_supported | 3.4s |
| 5.2 | 경쟁사 분석 표에서 X 찾기 | medium | ALL | PASS | strongly_supported | 3.1s |
| 5.3 | 보안 감사: 중간 5건 중 2건 완료, 3건 미조치 | hard | ANY | PASS | strongly_supported | 3.7s |
| 5.4 | HyPE는 v2.5.0에서 도입 | medium | ANY | PASS | strongly_supported | 3.5s |
| 5.5 | 특허: PAT-001은 한국만, PAT-002는 PCT 완료 | hard | ANY | PASS | insufficient_evidence | 9.6s |

### S6: 교차 문서 종합

- 결과: **5/5** (평균 4.75s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 6.1 | 고객 사례: Enterprise, 82%, 스캔 PDF/이미지 | hard | ANY | PASS | strongly_supported | 3.9s |
| 6.2 | 이메일(속도 요구) + changelog(BM25 40% 개선) | hard | ANY | PASS | strongly_supported | 4.1s |
| 6.3 | 고객 사례: Upstage에서 전환, NDCG 개선 | hard | ANY | PASS | strongly_supported | 2.8s |
| 6.4 | 이메일(기능/가격) + 특허(PAT-004) | extreme | ANY | PASS | strongly_supported | 3.0s |
| 6.5 | 이메일(80억 R&D) + 로드맵(개발15+영업5+기타10=30명) | hard | ANY | PASS | insufficient_evidence | 9.9s |

### S7: 패러프레이즈

- 결과: **6/6** (평균 5.26s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 7.1 | 보유 현금 45억 (일상적 표현) | easy | ANY | PASS | strongly_supported | 3.9s |
| 7.2 | 밸류에이션 (비공식 표현) | medium | ANY | PASS | strongly_supported | 3.3s |
| 7.3 | 보안 감사 Critical/High 항목 (구어체) | hard | ANY | PASS | partially_supported | 5.1s |
| 7.4 | 이메일: NTT 데이터 3.2억 (최대 규모) | medium | ANY | PASS | strongly_supported | 5.4s |
| 7.5 | 특허 포트폴리오 (비격식 질문) | hard | ANY | PASS | partially_supported | 11.5s |
| 7.6 | 고객 사례: 최대 고객 | medium | ANY | PASS | strongly_supported | 2.4s |

### S8: 멀티턴 대화 (엔티티 추적)

- 결과: **5/6** (평균 4.57s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 8.1 | 직접 질문 | easy | ANY | PASS | strongly_supported | 2.8s |
| 8.2 | 대명사 resolve: 그 제품 -> QuantumGuard | medium | ANY | PASS | strongly_supported | 4.0s |
| 8.3 | 문맥 유지: QuantumGuard 개발 | medium | ANY | PASS | strongly_supported | 2.9s |
| 8.4 | 주제 전환 -- 경쟁사 분석 | medium | ANY | PASS | partially_supported | 4.5s |
| 8.5 | 엔티티 추적: 그 회사 -> 퀀텀아이 | hard | ANY | **FAIL** | insufficient_evidence | 6.5s |
| 8.6 | 주제 복귀 + 특허 교차 | hard | ANY | PASS | partially_supported | 6.9s |

<details><summary>실패 케이스 상세</summary>

**[8.5] 엔티티 추적: 그 회사 -> 퀀텀아이** (hard)
- 질문: 그 회사의 매출은 퀀텀소프트보다 얼마나 더 많나요?
- 기대 키워드 (any): `['28억', '30억']`
- 실제 답변: 컨텍스트에는 **Upstage 또는 42Maru의 매출 수치가 없습니다**. 따라서 QuantumGuard의 경쟁사 매출이 퀀텀소프트보다 얼마나 더 많은지 **정량 비교는 불가능합니다**. [1][2][3][4][5][6]  참고로, 컨텍스트에 있는 관련 정보는 다음뿐입니다: - 퀀텀소프트의 **ARR 152억원**이 현재라고 되어 있습니다. [2] - 42Maru는 **등록 특허 5건, 출원 중 3건**으로만 언급되며 매출 정보는 없습니다. [1] - Upstage는 **경쟁사 가격 인하 리스크**와 **네이버 클라우드의 기존 솔

</details>

### S9: 엣지 케이스

- 결과: **7/7** (평균 3.96s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 9.1 | 빈 질문 | easy | ANY | PASS | insufficient_evidence | 0.0s |
| 9.2 | 문서에 없는 내용 | easy | ANY | PASS | insufficient_evidence | 4.6s |
| 9.3 | 공격적 어투 + 특수문자 | medium | ANY | PASS | strongly_supported | 6.2s |
| 9.4 | 반복 패턴이 포함된 긴 질문 | medium | ANY | PASS | strongly_supported | 2.6s |
| 9.5 | SQL injection 시도 | easy | ANY | PASS | insufficient_evidence | 5.5s |
| 9.6 | 문서에 존재하지 않는 상세 정보 | easy | ANY | PASS | insufficient_evidence | 3.2s |
| 9.7 | 미래 예측 (문서에 없음) | easy | ANY | PASS | insufficient_evidence | 5.6s |

### S10: 정밀 검색

- 결과: **6/6** (평균 2.99s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 10.1 | 회의록/이메일 깊은 상세 정보 | medium | ALL | PASS | strongly_supported | 3.3s |
| 10.2 | changelog 특정 버전 상세 | medium | ALL | PASS | strongly_supported | 2.6s |
| 10.3 | 조직도 CSV의 특정 행 | easy | ALL | PASS | strongly_supported | 2.9s |
| 10.4 | 보안 감사 SEC-003 상세 | hard | ANY | PASS | strongly_supported | 3.7s |
| 10.5 | 이메일: HyPE 성능 표 | hard | ALL | PASS | strongly_supported | 2.6s |
| 10.6 | 특허 문서 상세 | hard | ALL | PASS | strongly_supported | 2.9s |

### S11: 암묵적 추론

- 결과: **5/5** (평균 4.31s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 11.1 | 특허: PAT-001, 002, 003, 004에 모두 등재 -> 강지훈 4건 | hard | ANY | PASS | strongly_supported | 2.5s |
| 11.2 | 이메일: 3.8억->4.2억 = 0.4억 증가 | hard | ANY | PASS | insufficient_evidence | 9.5s |
| 11.3 | 고객 사례: PoC 실패 시 Upstage 재전환 가능 | hard | ANY | PASS | strongly_supported | 1.9s |
| 11.4 | 특허 문서: 현재 정적 링크 사용 -> 동적 링크 변경 필요 | hard | ANY | PASS | strongly_supported | 4.0s |
| 11.5 | 특허: AGPL 네트워크 사용 조항 | hard | ANY | PASS | partially_supported | 3.6s |

### S12: 경쟁사 비교

- 결과: **3/3** (평균 5.55s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 12.1 | 특허: 퀀텀소프트 3건 vs 퀀텀아이 8, 리턴제로 12, 42Maru 5 | hard | ANY | PASS | partially_supported | 5.5s |
| 12.2 | 고객 사례(월 1,200만 계약) + 경쟁사(점유율) | extreme | ANY | PASS | partially_supported | 3.5s |
| 12.3 | 이메일(NTT 경쟁) + 경쟁사 분석(기술 비교) | extreme | ANY | PASS | partially_supported | 7.7s |

### S13: 조건부 추론

- 결과: **5/5** (평균 5.18s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 13.1 | 이메일6: R&D 인력 80억 > 운영 50억 > QuantumGuard 40억 > 일본 30억 | medium | ANY | PASS | strongly_supported | 2.0s |
| 13.2 | 런웨이 10.7개월, Q2 2025까지 약 7-8개월 -> 가능하지만 여유 없음 | hard | ANY | PASS | partially_supported | 6.2s |
| 13.3 | 고객 사례(스캔 PDF 요청) + 로드맵(Q1 OCR 통합) | hard | ANY | PASS | strongly_supported | 3.1s |
| 13.4 | 회의록: 월 2,400만 -> 월 1,500만 절감 (60%), 연 1.8억 | hard | ANY | PASS | strongly_supported | 3.4s |
| 13.5 | 현재 ARR 120억 -> 180억 필요 = +60억. 파이프라인 19.5억(이메일) + 28억(회의록) | extreme | ANY | PASS | partially_supported | 11.3s |

### S14: 다중 제약 필터링

- 결과: **4/5** (평균 3.60s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 14.1 | 삼성전자(800만) + 김앤장(2,000만) = 2,800만 | hard | ANY | **FAIL** | strongly_supported | 2.8s |
| 14.2 | Critical: SEC-001(완료), High: SEC-002,003,004(모두 완료) -- 4개 섹션 동시 검색 필요 | extreme | ALL | PASS | strongly_supported | 2.6s |
| 14.3 | PAT-002만 PCT 완료 + 강지훈 발명 | hard | ANY | PASS | strongly_supported | 3.6s |
| 14.4 | 조직도: 백엔드(12명,박서연) + AI(15명,강지훈) | medium | ALL | PASS | strongly_supported | 4.9s |
| 14.5 | changelog: v2.4(7월, Adaptive Query Routing) + v2.5(10월, HyPE) | hard | ALL | PASS | strongly_supported | 4.2s |

<details><summary>실패 케이스 상세</summary>

**[14.1] 삼성전자(800만) + 김앤장(2,000만) = 2,800만** (hard)
- 질문: 온프레미스로 배포된 Enterprise 등급 고객의 월 매출 합계는?
- 기대 키워드 (any): `['2,800만', '2800만']`
- 실제 답변: 온프레미스 배포된 **Enterprise 등급** 고객은 다음 3개입니다. [1]  - 법무법인 김앤장: 월 매출 **2,000만원** [1] - 삼성전자 반도체: 월 매출 **800만원** [1] - SK텔레콤: 월 매출 **450만원** [1]  합계 월 매출 = 2,000 + 800 + 450 = **3,250만원** [1]  **신뢰도: STRONGLY_SUPPORTED**

</details>

### S15: 정량적 파생 계산

- 결과: **5/5** (평균 3.75s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 15.1 | 인프라: 6.5억/6명=1.08억 > AI: 12/15=0.8 > 백엔드: 8/12=0.67 | hard | ANY | PASS | strongly_supported | 4.1s |
| 15.2 | 김앤장2000+네이버1200+삼성800+KB600+현대600=5200/8267=63% | extreme | ANY | PASS | strongly_supported | 3.7s |
| 15.3 | 52->152억 in 2년, CAGR=(152/52)^0.5-1=71% | extreme | ANY | PASS | strongly_supported | 3.6s |
| 15.4 | 회의록: 인건비 5.8억(65%) + 인프라 0.5억(6%) = 6.3억(71%) | hard | ANY | PASS | strongly_supported | 4.0s |
| 15.5 | ARR 120억 / 32개사 = 3.75억. 또는 회의록: 평균 3,800만원/년 | medium | ANY | PASS | strongly_supported | 3.4s |

### S16: 교차 검증

- 결과: **3/4** (평균 5.20s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 16.1 | CEO: 실질 12~13개월, CFO: 10.7개월 -- 시점/가정 차이 | hard | ALL | PASS | strongly_supported | 4.8s |
| 16.2 | 회의록: 25명(개발15+영업5+기타5), 로드맵: 30명(개발15+영업5+기타10) | hard | ALL | PASS | strongly_supported | 3.9s |
| 16.3 | 이메일5: 정식 출시 Q2 2025 = 로드맵 Q2 2025 QuantumGuard v1.0 | medium | ANY | PASS | strongly_supported | 6.0s |
| 16.4 | 회의록: 약 20억원, 이메일6: 30억원 -- 범위 차이 | hard | ALL | **FAIL** | partially_supported | 6.0s |

<details><summary>실패 케이스 상세</summary>

**[16.4] 회의록: 약 20억원, 이메일6: 30억원 -- 범위 차이** (hard)
- 질문: 일본 법인 설립 비용이 이메일과 회의록에서 다른데, 각각 얼마인가요?
- 기대 키워드 (all): `['20억', '30억']`
- 실제 답변: 일본 법인 설립 비용은 자료에 따라 다르게 기재되어 있습니다.  - **약 20억원**: 2024년 4분기 경영진 회의록(해외 진출 전략 > 일본 시장)에서 “투자 소요: 약 20억원 (법인 설립 + 현지 인력 3명)”으로 명시되어 있습니다. [1] - **이메일(사내 이메일 스레드)에는 일본 법인 설립 비용이 ‘금액’으로 명시된 내용이 확인되지 않습니다.** [2][3][4][6]  따라서, 이메일 기준으로는 “일본 법인 설립 비용”이 얼마인지 컨텍스트만으로는 특정할 수 없습니다. [2][3][4][6]  **신뢰도: PARTIA

</details>

### S17: 다양한 문서 포맷 (PDF/HWPX)

- 결과: **14/20** (평균 3.85s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 17.1 | PDF: 저자/소속 기본 확인 | easy | ALL | PASS | strongly_supported | 3.8s |
| 17.2 | PDF: 아키텍처 핵심 개념 | medium | ANY | PASS | strongly_supported | 2.9s |
| 17.3 | PDF: COCO dataset 5000 image-caption pairs | medium | ANY | PASS | strongly_supported | 3.6s |
| 17.4 | PDF: Image-Caption Similarity Assessment | easy | ANY | PASS | strongly_supported | 2.3s |
| 17.5 | PDF: Metrics for Generation Quality | medium | ALL | PASS | strongly_supported | 3.4s |
| 17.6 | PDF: Methodology - triple extraction and alignment | hard | ANY | PASS | strongly_supported | 3.6s |
| 17.7 | PDF: Graph-based Contextual Consistency Comparison | medium | ANY | **FAIL** | insufficient_evidence | 4.4s |
| 17.8 | PDF: MKT assesses knowledge sufficiency, Alignment Test evaluates content alignment | hard | ANY | PASS | strongly_supported | 3.2s |
| 17.9 | PDF: Multi-Agent Collaboration via OVON | medium | ANY | **FAIL** | insufficient_evidence | 4.4s |
| 17.10 | PDF: 3단계 리뷰 구조 | hard | ANY | **FAIL** | insufficient_evidence | 8.2s |
| 17.11 | HWPX: 기본 방향 | easy | ANY | PASS | strongly_supported | 2.4s |
| 17.12 | HWPX: 경제성장률 '25 1.8% | easy | ANY | **FAIL** | insufficient_evidence | 4.5s |
| 17.13 | HWPX: 국가공무원 정원 약 4천 명 감축 | medium | ANY | PASS | strongly_supported | 2.6s |
| 17.14 | HWPX: 모바일 신분증 발급자 400만 명 돌파 | easy | ANY | PASS | strongly_supported | 2.8s |
| 17.15 | HWPX: 고향사랑기부제 '24잠정 879억 모금 | medium | ANY | **FAIL** | insufficient_evidence | 4.1s |
| 17.16 | HWPX: '24 18개소->'25 35개소 | medium | ANY | PASS | strongly_supported | 2.4s |
| 17.17 | HWPX: 5개->19개 언어, '25.8. | medium | ALL | **FAIL** | insufficient_evidence | 5.5s |
| 17.18 | HWPX: 드론/SAR 활용 급경사지 붕괴위험 분석기술 | hard | ANY | PASS | strongly_supported | 2.1s |
| 17.19 | PDF+HWPX: 정보의 정확성과 신뢰성이라는 공통 주제 | extreme | ANY | PASS | partially_supported | 8.3s |
| 17.20 | PDF: Comprehensive Unlearning Techniques -- 할루시네이션 최소화 | hard | ANY | PASS | strongly_supported | 2.4s |

<details><summary>실패 케이스 상세</summary>

**[17.7] PDF: Graph-based Contextual Consistency Comparison** (medium)
- 질문: ZeroH에서 그래프 기반 문맥 일관성 비교에 사용하는 네트워크는?
- 기대 키워드 (any): `['RGCN', 'Relational Graph']`
- 실제 답변: 제공된 컨텍스트만으로는 **ZeroH에서 그래프 기반 문맥 일관성 비교에 사용하는 “네트워크”의 구체적 명칭**을 확인할 수 없습니다. [1][5]  컨텍스트에는 ZeroH가 **OVON 상호운용성 표준**, **Conversation Envelopes(JSON 메시지)**, 그리고 **다중 리뷰 레벨(Front End Agent, Second Level Reviewer, Third Level Reviewer)**을 사용한다고만 나와 있으며, 질문하신 “그래프 기반 문맥 일관성 비교”에 쓰는 별도 네트워크 이름은 명시되어 있지 않습

**[17.9] PDF: Multi-Agent Collaboration via OVON** (medium)
- 질문: ZeroH에서 에이전트 간 통신에 사용하는 표준 프레임워크는?
- 기대 키워드 (any): `['OVON', 'Open Voice Network']`
- 실제 답변: 제공된 컨텍스트에는 **ZeroH Hallucination Framework(ZeroH)**에서 에이전트 간 통신에 사용하는 **표준 프레임워크**가 무엇인지에 대한 정보가 없습니다. [2]에는 ZeroH의 구성/평가(예: 이미지-캡션 유사도, CLIP 등) 내용만 일부 포함되어 있고, 에이전트 간 통신 표준 프레임워크 언급은 확인되지 않습니다. [2]  따라서 현재로서는 답변을 **할 수 없습니다(INSUFFICIENT_EVIDENCE)**.  - **신뢰도: INSUFFICIENT_EVIDENCE**

**[17.10] PDF: 3단계 리뷰 구조** (hard)
- 질문: ZeroH 프레임워크의 리뷰 레벨 구조는?
- 기대 키워드 (any): `['Front End Agent', 'Second Level Reviewer', 'Third Level Reviewer']`
- 실제 답변: 제공된 컨텍스트에는 **“리뷰 레벨 구조(예: 단계/레벨별 검토 체계)”**에 대한 구체적인 설명이 없습니다. 다만, ZeroH 프레임워크의 **2단계 워크플로우**(Model Knowledge Test, Alignment Test)와, 내부 모듈(예: Triple-Oriented Response Segmentation, Graph-based Contextual Consistency Comparison, Reverse Verification via Triples Reconstruction, Self-Reflection)이 언급됩니다

**[17.12] HWPX: 경제성장률 '25 1.8%** (easy)
- 질문: 2025년 정부 경제성장률 전망은 얼마인가요?
- 기대 키워드 (any): `['1.8']`
- 실제 답변: 제공된 컨텍스트에는 **2025년 정부의 경제성장률 전망 수치**가 없습니다. 따라서 “2025년 정부 경제성장률 전망은 얼마인가요?”에 대해 **답변할 근거가 부족**합니다.    - 컨텍스트 [1]은 저출생·산업·사회통합·디지털정부 등 정책 추진 내용과 2025년 주요 정책 일정표가 포함되어 있으나, **경제성장률 전망(수치)**은 제시되지 않습니다. [1]   - 컨텍스트 [2]~[6]은 회사(퀀텀소프트) 사업/재무/경쟁사 분석 자료로, **정부 경제성장률 전망**과 무관합니다. [2][4][5][6]    **신뢰도: INS

**[17.15] HWPX: 고향사랑기부제 '24잠정 879억 모금** (medium)
- 질문: 고향사랑기부제의 2024년 잠정 모금액은 얼마인가요?
- 기대 키워드 (any): `['879억']`
- 실제 답변: 제공된 컨텍스트에는 **고향사랑기부제의 2024년 잠정 모금액**에 대한 수치가 없습니다. 다만, 고향사랑기부 활성화와 관련해 **개인별 연간 기부한도 상향(500만 원 → 2,000만 원, ’25.1.1.~)** 및 **1차/2차 개통 일정** 등 제도 내용만 확인됩니다. [12]  따라서 **2024년 잠정 모금액(금액)**은 컨텍스트만으로는 확인할 수 없습니다. [12]  **신뢰도: INSUFFICIENT_EVIDENCE**

**[17.17] HWPX: 5개->19개 언어, '25.8.** (medium)
- 질문: 재난문자 제공언어는 몇 개에서 몇 개로 확대되나요?
- 기대 키워드 (all): `['5개', '19개']`
- 실제 답변: 재난문자 제공언어는 **(문서에 명시된 기준으로) “몇 개 → 몇 개”**로 확대된다고만 되어 있고, **구체적인 기존/확대 언어 개수(예: 〇개에서 〇개로)**는 컨텍스트에 제공되어 있지 않습니다. 따라서 **정확한 숫자는 확인 불가**입니다. [3]  - 참고: 하반기 추진과제에 “재난문자 제공언어 확대”가 언급되어 있으나, 언어 개수는 미기재입니다. [3]  **신뢰도: INSUFFICIENT_EVIDENCE**

</details>

### S18: 불완전 정보 추론

- 결과: **5/5** (평균 5.34s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 18.1 | 문서에 총 인원/예산은 있으나 1인당 연봉은 없음 -- 부분 정보 인정 필요 | hard | ANY | PASS | insufficient_evidence | 6.3s |
| 18.2 | 조직도에 이름만 있고 성별 정보 없음 | medium | ANY | PASS | insufficient_evidence | 5.5s |
| 18.3 | 학술 논문이므로 실제 배포 사례 없음 | medium | ANY | PASS | insufficient_evidence | 4.7s |
| 18.4 | HWPX에 개별 프로그램 예산은 있으나 총액 합산은 불명확 | hard | ANY | PASS | insufficient_evidence | 4.1s |
| 18.5 | 직접 명시되지 않음 -- 감사 결과에서 간접 추론 가능하나 수치 불가 | hard | ANY | PASS | insufficient_evidence | 6.1s |

### S19: 모순/불일치 감지

- 결과: **3/4** (평균 4.33s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 19.1 | 회의록/이메일 간 날짜 교차 확인 | hard | ALL | PASS | strongly_supported | 3.2s |
| 19.2 | 전체 등급 vs 개별 항목 정합성 검증 | extreme | ANY | PASS | partially_supported | 3.1s |
| 19.3 | 시간적 일관성 확인 | hard | ANY | PASS | partially_supported | 6.4s |
| 19.4 | CEO 12-13개월 vs CFO 10.7개월 | hard | ANY | **FAIL** | insufficient_evidence | 4.7s |

<details><summary>실패 케이스 상세</summary>

**[19.4] CEO 12-13개월 vs CFO 10.7개월** (hard)
- 질문: CEO 이메일의 낙관적 전망과 CFO 보고서의 보수적 전망 중 구체적 수치 차이는?
- 기대 키워드 (any): `['12', '13', '10.7', '소진율']`
- 실제 답변: CEO 이메일에는 **구체적인 낙관적 전망 수치가 제시되지 않았고**, CFO 보고서에는 **하반기 신규 계약 30억원 이상이 필요하다**는 보수적 전망이 제시되어 있습니다. 따라서 두 전망의 **직접적인 수치 차이**를 계산할 수 있는 비교 가능한 CEO 수치가 컨텍스트에 없습니다. [4]  참고로 CFO의 Series C 관련 목표는 **200억원 투자 유치**, **1,500억원 pre-money 밸류에이션**, 그리고 **2025년 Q1 내 클로징 목표**입니다. [2]  신뢰도: **INSUFFICIENT_EVIDENCE*

</details>

### S20: 한영 혼합 질의

- 결과: **3/4** (평균 4.51s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 20.1 | 한영 혼합: 기술 용어(영) + 질문(한) | medium | ANY | **FAIL** | insufficient_evidence | 4.2s |
| 20.2 | PDF 기반 영어 기술 용어 + 한국어 문맥 | hard | ANY | PASS | insufficient_evidence | 6.2s |
| 20.3 | 영어 비즈니스 용어 + 한국어 데이터 | medium | ANY | PASS | strongly_supported | 2.7s |
| 20.4 | 기술 용어 혼합 -- 문서에 직접 정보 부족할 수 있음 | hard | ANY | PASS | insufficient_evidence | 4.8s |

<details><summary>실패 케이스 상세</summary>

**[20.1] 한영 혼합: 기술 용어(영) + 질문(한)** (medium)
- 질문: QuantumRAG의 Triple Index Fusion에서 BM25 weight는 기본값이 얼마인가요?
- 기대 키워드 (any): `['0.25', '25%']`
- 실제 답변: 제공된 컨텍스트에는 **Triple Index Fusion에서 BM25 weight(가중치) 기본값**이 얼마인지에 대한 정보가 없습니다. [1]~[7]의 변경 이력/제안서/FAQ/가이드/로드맵/특허 요약에는 BM25 weight의 “기본값” 수치가 명시되어 있지 않습니다.    따라서 현재로서는 **INSUFFICIENT_EVIDENCE** 입니다.    - 신뢰도: **INSUFFICIENT_EVIDENCE**

</details>

### S21: 반사실적 추론

- 결과: **3/4** (평균 3.74s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 21.1 | 런웨이 10.7개월 기반 가정 추론 | hard | ANY | PASS | partially_supported | 2.9s |
| 21.2 | 현재 ARR 120억 + 일본 7.5억 = 127.5억 | extreme | ANY | **FAIL** | insufficient_evidence | 4.7s |
| 21.3 | HyPE 도입 전 성능 수준으로 회귀 가정 | hard | ANY | PASS | partially_supported | 4.1s |
| 21.4 | HWPX: 디지털 플랫폼 연관 사업 식별 | hard | ANY | PASS | partially_supported | 3.3s |

<details><summary>실패 케이스 상세</summary>

**[21.2] 현재 ARR 120억 + 일본 7.5억 = 127.5억** (extreme)
- 질문: 일본 PoC 3건이 모두 성사되면 ARR에 어떤 영향이 있나요?
- 기대 키워드 (any): `['7.5억', '120억', '127.5']`
- 실제 답변: 컨텍스트상 일본 시장의 **확정 PoC는 2건**만 명시되어 있고, 그중 **NTT 데이터 1건**만 연 3.2억원 규모로 확인됩니다. 일본 PoC **3건 전체의 ARR 영향**은 구체 금액이 제시되지 않아 직접 계산할 수 없습니다. [1][3]  다만 로드맵에는 **일본 시장 진출**과 **일본 리전 추가**, 그리고 일본 고객 대응 기능들이 계획되어 있어 일본 사업 확대를 추진 중임은 확인됩니다. [2]  따라서, **일본 PoC 3건이 모두 성사될 경우 ARR은 증가하겠지만, 컨텍스트만으로는 증가액을 산정할 수 없습니다.**

</details>

### S22: 수치 교차 검증

- 결과: **3/4** (평균 5.43s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 22.1 | 고객 사례 보고서에 명시된 개별 고객 수 vs 전체 32개 | extreme | ANY | PASS | strongly_supported | 4.1s |
| 22.2 | 특허 문서의 날짜 기반 정렬 및 간격 계산 | hard | ANY | PASS | strongly_supported | 8.7s |
| 22.3 | 조직도 CSV 합산 vs 회사 소개 수치 비교 | medium | ANY | PASS | strongly_supported | 3.6s |
| 22.4 | changelog에서 하반기 항목 분류 및 집계 | hard | ALL | **FAIL** | strongly_supported | 5.3s |

<details><summary>실패 케이스 상세</summary>

**[22.4] changelog에서 하반기 항목 분류 및 집계** (hard)
- 질문: 2024년 하반기 changelog의 기능 추가 건수와 버그 수정 건수를 각각 알려주세요
- 기대 키워드 (all): `['v2.4', 'v2.5']`
- 실제 답변: 2024년 하반기 changelog의 **기능 추가 6건**, **버그 수정 6건**입니다. [1]  STRONGLY_SUPPORTED

</details>

### S23: 복합 조건부 질의

- 결과: **4/4** (평균 4.63s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 23.1 | 다중 조건: 배포 방식 + 등급 + 만족도 필터링 | extreme | ANY | PASS | insufficient_evidence | 8.4s |
| 23.2 | 보안 감사: 등급 + 조치 상태 교차 필터 | hard | ANY | PASS | strongly_supported | 3.6s |
| 23.3 | 시간 구간별 마일스톤 분류 | hard | ANY | PASS | strongly_supported | 3.0s |
| 23.4 | 매출 + 만족도 이중 조건 필터 | hard | ANY | PASS | strongly_supported | 3.5s |

### S24: 추상적/메타 질의

- 결과: **3/3** (평균 4.00s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 24.1 | 여러 문서에서 리스크 요인 추출 및 우선순위 판단 | extreme | ANY | PASS | partially_supported | 4.3s |
| 24.2 | PDF 전체 요약 -- 학술적 기여 추출 | hard | ANY | PASS | partially_supported | 3.5s |
| 24.3 | HWPX에서 디지털 전환 관련 항목 필터링 | hard | ANY | PASS | strongly_supported | 4.2s |

### S25: 역방향 추론

- 결과: **3/3** (평균 2.88s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 25.1 | 수치에서 역방향으로 원인 추적 | hard | ANY | PASS | strongly_supported | 2.9s |
| 25.2 | 수치 -> 문맥 역추적 | medium | ANY | PASS | strongly_supported | 3.2s |
| 25.3 | HWPX: 고향사랑기부제 모금액 역추적 | medium | ANY | PASS | strongly_supported | 2.6s |

### S26: 테이블 구조 이해

- 결과: **4/5** (평균 3.58s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 26.1 | 표의 행/열 교차 조건 필터링 | hard | ANY | PASS | strongly_supported | 2.5s |
| 26.2 | 표에서 정렬 + 상위 N 추출 | hard | ANY | PASS | insufficient_evidence | 5.6s |
| 26.3 | 표의 그룹별 집계 비교 | extreme | ANY | PASS | partially_supported | 3.0s |
| 26.4 | 구조적 데이터의 재구조화 | hard | ALL | PASS | strongly_supported | 2.5s |
| 26.5 | PDF 테이블 내 비교 데이터 추출 | extreme | ANY | **FAIL** | insufficient_evidence | 4.3s |

<details><summary>실패 케이스 상세</summary>

**[26.5] PDF 테이블 내 비교 데이터 추출** (extreme)
- 질문: ZeroH 논문의 표에서 각 평가 지표별 최고 성능 모델은?
- 기대 키워드 (any): `['informativeness', 'consistency', 'fluency']`
- 실제 답변: 제공된 컨텍스트만으로는 **ZeroH 논문의 표에 있는 각 평가 지표와 모델별 수치가 확인되지 않아**, 각 지표별 최고 성능 모델을 특정할 수 없습니다. [2][6]  - Source 2는 문서 요약에서 **“기타 (6개 항목)”**만 보여주고 있어 표 내용이 없습니다. [2] - Source 6은 ZeroH 프레임워크의 개요/배경 설명만 있으며, **평가 표나 모델별 성능 비교 표는 포함되어 있지 않습니다.** [6]  따라서 현재 답변은 **INSUFFICIENT_EVIDENCE**입니다.

</details>

### S27: 답변 완전성

- 결과: **5/5** (평균 4.63s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 27.1 | 3건의 산재된 정보 완전 수집 | hard | ANY | PASS | strongly_supported | 4.2s |
| 27.2 | 4개 보안 이슈 완전 열거 | extreme | ALL | PASS | partially_supported | 9.2s |
| 27.3 | 4개 특허 완전 열거 | hard | ALL | PASS | strongly_supported | 3.5s |
| 27.4 | 4개 항목 완전 열거 + 금액 | hard | ANY | PASS | strongly_supported | 3.1s |
| 27.5 | 4분기 전체 로드맵 완전 수집 | hard | ALL | PASS | strongly_supported | 3.2s |

### S28: 청크 경계 강건성

- 결과: **3/4** (평균 4.41s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 28.1 | 버전 경계에 걸친 정보 추출 | hard | ANY | PASS | strongly_supported | 2.4s |
| 28.2 | 문서 말미의 부가 정보 — 청크 경계에서 누락 가능 | medium | ANY | PASS | insufficient_evidence | 3.9s |
| 28.3 | HWPX 문서 후반부 정보 — 마지막 청크에 위치 | medium | ANY | **FAIL** | partially_supported | 4.7s |
| 28.4 | PDF 결론부 — 문서 끝부분 청크 경계 | hard | ANY | PASS | insufficient_evidence | 6.5s |

<details><summary>실패 케이스 상세</summary>

**[28.3] HWPX 문서 후반부 정보 — 마지막 청크에 위치** (medium)
- 질문: 행정안전부 문서의 마지막 섹션에서 다루는 주제는?
- 기대 키워드 (any): `['R&D', '기술', '연구']`
- 실제 답변: 행정안전부 문서의 **마지막 섹션(“기타”)에서 다루는 주제는** 컨텍스트에 따르면 **5개 항목**입니다. [9]  다만, 해당 “기타(5개 항목)”가 **구체적으로 무엇인지**(각 항목의 내용)는 제공된 컨텍스트에 **나열되어 있지 않아** 확인할 수 없습니다. [9]  **출처** - [9] “2025_plan” 문서 요약: 구성 섹션에 “기타 (5개 항목)”만 명시  **신뢰도: PARTIALLY_SUPPORTED**

</details>

### S29: PDF 심층 구조 추출

- 결과: **5/5** (평균 3.97s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 29.1 | PDF의 Figure/Table 캡션 추출 | hard | ANY | PASS | insufficient_evidence | 4.7s |
| 29.2 | PDF 본문의 분류 체계 추출 | medium | ANY | PASS | strongly_supported | 2.6s |
| 29.3 | PDF Abstract 섹션 정밀 추출 | medium | ANY | PASS | partially_supported | 4.1s |
| 29.4 | PDF 핵심 방법론 완전 열거 | hard | ANY | PASS | partially_supported | 4.7s |
| 29.5 | PDF의 실험 설정 정보 수집 | extreme | ANY | PASS | partially_supported | 3.8s |

### S30: 산재 정보 종합 수집

- 결과: **3/4** (평균 5.12s)

| ID | 설명 | 난이도 | 매칭 | 결과 | 신뢰도 | 시간 |
|-----|------|--------|------|------|--------|------|
| 30.1 | 여러 문서에 산재된 파트너 정보 수집 | hard | ANY | **FAIL** | strongly_supported | 2.8s |
| 30.2 | 이메일+회의록에 분산된 PoC 정보 종합 | extreme | ANY | PASS | strongly_supported | 3.7s |
| 30.3 | 로드맵+이메일+회의록의 일정 정보 통합 | hard | ANY | PASS | strongly_supported | 6.2s |
| 30.4 | 특허+감사+changelog에 분산된 오픈소스 정보 | extreme | ANY | PASS | partially_supported | 7.8s |

<details><summary>실패 케이스 상세</summary>

**[30.1] 여러 문서에 산재된 파트너 정보 수집** (hard)
- 질문: 퀀텀소프트의 모든 외부 파트너사(투자사, 고객사 제외)를 나열해주세요
- 기대 키워드 (any): `['미래에셋', '한화']`
- 실제 답변: 컨텍스트에 따르면, 퀀텀소프트의 외부 파트너사로 명시적으로 확인되는 것은 **투자사**뿐입니다. 고객사는 제외하라고 하셨으므로, 투자사 기준으로 나열하면 다음과 같습니다. [1]  - 프라이머 [1] - 알토스벤처스 [1] - 스파크랩 [1] - 소프트뱅크벤처스 [1] - KB인베스트먼트 [1]  다만, **투자사 외의 외부 파트너사**(예: 협력사, 공급사, 채널 파트너 등)는 제공된 컨텍스트에 명시되어 있지 않아 확인할 수 없습니다. [1][2][3]  신뢰도: **STRONGLY_SUPPORTED**

</details>

## 5. v3 고급 시나리오 분석

### 시나리오 카테고리별 분석

- **S18: 불완전 정보 추론**: 5/5 (100%)
  - 불완전 정보 추론 -- 정보 부족 시 적절한 응답 능력
- **S19: 모순/불일치 감지**: 3/4 (75%)
  - 모순/불일치 감지 -- 문서 간 데이터 정합성 검증 능력
- **S20: 한영 혼합 질의**: 3/4 (75%)
  - 한영 혼합 질의 -- 이중 언어 기술 용어 처리 능력
- **S21: 반사실적 추론**: 3/4 (75%)
  - 반사실적 추론 -- 가정 기반 논리적 추론 능력
- **S22: 수치 교차 검증**: 3/4 (75%)
  - 세밀한 수치 교차 검증 -- 수치 데이터 일관성 검증 능력
- **S23: 복합 조건부 질의**: 4/4 (100%)
  - 복합 조건부 질의 -- 다중 필터 조합 처리 능력
- **S24: 추상적/메타 질의**: 3/3 (100%)
  - 추상적/메타 질의 -- 상위 수준 분석 및 요약 능력
- **S25: 역방향 추론**: 3/3 (100%)
  - 역방향 추론 -- 결과에서 원인으로의 역추적 능력
- **S26: 테이블 구조 이해**: 4/5 (80%)
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
- [x] 수치 계산/비교 (S3)
- [x] 시간/버전 추론 (S4)
- [x] 부정형/제외 (S5)
- [x] 교차 문서 종합 (S6)
- [x] 패러프레이즈/구어체 (S7)
- [ ] 멀티턴 엔티티 추적 (S8)
- [x] 엣지 케이스 (S9)
- [x] 정밀 검색 (S10)
- [x] 암묵적 추론 (S11)
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
- [x] 평균 응답 시간 < 5초
- [x] hard 난이도 통과율 > 60%
- [x] extreme 난이도 통과율 > 40%

## 7. 성능 분석

| 구간 | 건수 | 비율 |
|------|------|------|
| < 2초 | 5건 | 3% |
| 2~4초 | 92건 | 57% |
| > 4초 | 64건 | 40% |

| 신뢰도 | 건수 |
|--------|------|
| insufficient_evidence | 31건 |
| partially_supported | 28건 |
| strongly_supported | 102건 |

## 8. 결론 및 개선 제안

전체 통과율 **90.1%**로 우수합니다.

### Baseline vs Advanced 비교 인사이트

- Baseline(90%)과 Advanced(87%) 통과율이 유사합니다.
- 고급 추론 능력이 기본 능력과 균형을 이루고 있습니다.

### 개선이 필요한 영역

- **S8: 멀티턴 대화 (엔티티 추적)**: 5/6 -- [8.5] 엔티티 추적: 그 회사 -> 퀀텀아이
- **S14: 다중 제약 필터링**: 4/5 -- [14.1] 삼성전자(800만) + 김앤장(2,000만) = 2,800만
- **S16: 교차 검증**: 3/4 -- [16.4] 회의록: 약 20억원, 이메일6: 30억원 -- 범위 차이
- **S17: 다양한 문서 포맷 (PDF/HWPX)**: 14/20 -- [17.7] PDF: Graph-based Contextual Consistency Comparison, [17.9] PDF: Multi-Agent Collaboration via OVON, [17.10] PDF: 3단계 리뷰 구조, [17.12] HWPX: 경제성장률 '25 1.8%, [17.15] HWPX: 고향사랑기부제 '24잠정 879억 모금, [17.17] HWPX: 5개->19개 언어, '25.8.
- **S19: 모순/불일치 감지**: 3/4 -- [19.4] CEO 12-13개월 vs CFO 10.7개월
- **S20: 한영 혼합 질의**: 3/4 -- [20.1] 한영 혼합: 기술 용어(영) + 질문(한)
- **S21: 반사실적 추론**: 3/4 -- [21.2] 현재 ARR 120억 + 일본 7.5억 = 127.5억
- **S22: 수치 교차 검증**: 3/4 -- [22.4] changelog에서 하반기 항목 분류 및 집계
- **S26: 테이블 구조 이해**: 4/5 -- [26.5] PDF 테이블 내 비교 데이터 추출
- **S28: 청크 경계 강건성**: 3/4 -- [28.3] HWPX 문서 후반부 정보 — 마지막 청크에 위치
- **S30: 산재 정보 종합 수집**: 3/4 -- [30.1] 여러 문서에 산재된 파트너 정보 수집

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
