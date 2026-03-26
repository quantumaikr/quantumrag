# QuantumRAG API 기술 가이드

## 인증 (Authentication)

### API 키 발급
1. 관리자 콘솔(https://console.quantumsoft.ai)에 로그인
2. 설정 > API 키 관리에서 "새 키 발급" 클릭
3. 키 이름과 권한 범위를 설정
4. 발급된 키는 최초 1회만 표시되므로 안전하게 보관

### 인증 방식
모든 API 요청에 `Authorization: Bearer <API_KEY>` 헤더를 포함해야 합니다.

```bash
curl -H "Authorization: Bearer qr_live_abc123" https://api.quantumsoft.ai/v1/query
```

### 토큰 갱신
- API 키의 기본 유효기간: 90일
- 만료 30일 전부터 갱신 가능
- 갱신 API: `POST /v1/auth/refresh`
- 갱신 시 기존 키는 24시간 후 자동 만료

## 에러 코드

| 코드 | 설명 | 대응 방법 |
|------|------|----------|
| 400 | 잘못된 요청 형식 | 요청 본문의 JSON 형식을 확인하세요 |
| 401 | 인증 실패 | API 키가 유효한지 확인하세요 |
| 403 | 권한 없음 | API 키의 권한 범위를 확인하세요 |
| 404 | 리소스 없음 | 요청 경로와 문서 ID를 확인하세요 |
| 429 | Rate Limit 초과 | 기본 제한: 분당 60회, 일간 10,000회 |
| 500 | 서버 내부 오류 | support@quantumsoft.ai로 문의하세요 |

## Rate Limit 정책

- **Free 플랜**: 분당 10회, 일간 1,000회
- **Pro 플랜**: 분당 60회, 일간 10,000회
- **Enterprise 플랜**: 분당 300회, 일간 무제한
- 초과 시 429 응답과 함께 `Retry-After` 헤더 반환
- 헤더: `X-RateLimit-Remaining`, `X-RateLimit-Reset`

## 데이터 흐름 아키텍처

### Ingest Pipeline
1. **파싱**: 문서 업로드 → 포맷별 파서가 텍스트 추출
2. **청킹**: 텍스트 → 의미 단위로 분할 (기본 512 토큰)
3. **임베딩**: 각 청크를 벡터로 변환 (text-embedding-3-small)
4. **HyPE 생성**: 청크별 가상 질문 3개 생성
5. **인덱싱**: 벡터 DB + BM25 인덱스에 저장

### Query Pipeline
1. **라우팅**: 질문 복잡도 자동 분류 (SIMPLE/MEDIUM/COMPLEX)
2. **검색**: Triple Index Fusion (임베딩 + HyPE + BM25)
3. **리랭킹**: 관련성 재정렬 (MEDIUM/COMPLEX만)
4. **생성**: LLM이 컨텍스트 기반 답변 생성

## SDK 사용 예시

### Python SDK
```python
from quantumrag import Engine

engine = Engine()
engine.ingest("./documents")
result = engine.query("매출은 얼마인가요?")
print(result.answer)
```

### 스트리밍 응답
```python
async for token in engine.query_stream("질문"):
    print(token, end="")
```

## 배포 가이드

### Docker 배포
```bash
docker pull quantumsoft/quantumrag:latest
docker run -p 8000:8000 -e OPENAI_API_KEY=sk-xxx quantumsoft/quantumrag
```

### Kubernetes 배포
- 최소 사양: 2 CPU, 4GB RAM
- 권장 사양: 4 CPU, 8GB RAM, GPU (A10G)
- 헬스체크 엔드포인트: `GET /health`
- Readiness 프로브: `GET /ready`
