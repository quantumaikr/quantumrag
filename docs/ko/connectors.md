# 데이터 커넥터

> 로컬 파일, 클라우드 스토리지, SaaS 플랫폼에서 문서를 인제스트하세요.

---

## 개요

QuantumRAG는 다양한 데이터 소스를 위한 커넥터를 제공합니다. 모든 커넥터는 비동기 지원, 재귀 탐색, 메타데이터 보존을 포함하는 공통 인터페이스를 구현합니다.

---

## 지원 커넥터

| 커넥터 | 소스 | 인증 |
|--------|------|------|
| **File** | 로컬 파일 시스템 | 없음 |
| **URL** | HTTP/HTTPS URL | 없음 |
| **S3** | AWS S3 버킷 | AWS 자격 증명 |
| **Google Drive** | Google Drive 폴더 | OAuth2 / 서비스 계정 |
| **Notion** | Notion 데이터베이스 | 통합 토큰 |

---

## File 커넥터

로컬 파일 시스템 경로에서 인제스트.

```python
engine = Engine()
engine.ingest("./docs")                    # 디렉토리
engine.ingest("./report.pdf")              # 단일 파일
engine.ingest("./docs", recursive=True)    # 재귀 탐색
```

CLI:

```bash
quantumrag ingest ./docs --recursive
quantumrag ingest ./report.pdf
```

### 감시 모드

디렉토리의 변경 사항을 모니터링하고 자동 인제스트:

```bash
quantumrag ingest ./docs --watch
```

---

## URL 커넥터

웹 URL에서 인제스트.

```python
engine.ingest("https://example.com/report.pdf")
```

HTTP/HTTPS를 지원하며 형식 자동 감지.

---

## S3 커넥터

AWS S3 버킷에서 인제스트.

**사전 조건:**
- AWS 자격 증명 설정 (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
- 또는 S3 읽기 권한이 있는 IAM 역할

```python
from quantumrag.connectors.s3 import S3Connector

connector = S3Connector(
    bucket="my-documents",
    prefix="reports/",
    region="us-east-1",
)

documents = await connector.list_documents()
for doc in documents:
    content = await connector.download(doc.id)
```

---

## Google Drive 커넥터

Google Drive 폴더에서 인제스트.

**사전 조건:**
- Drive API가 활성화된 Google Cloud 프로젝트
- OAuth2 자격 증명 또는 서비스 계정 키

```python
from quantumrag.connectors.gdrive import GDriveConnector

connector = GDriveConnector(
    folder_id="1ABC...",
    credentials_path="credentials.json",
)

documents = await connector.list_documents()
```

---

## Notion 커넥터

Notion 데이터베이스 및 페이지에서 인제스트.

**사전 조건:**
- Notion 통합 토큰 (`NOTION_TOKEN`)
- 대상 데이터베이스/페이지에 통합 추가

```python
from quantumrag.connectors.notion import NotionConnector

connector = NotionConnector(
    database_id="abc123...",
    token="secret_...",
)

documents = await connector.list_documents()
```

---

## 커넥터 인터페이스

모든 커넥터가 구현하는 기본 프로토콜:

```python
class Connector(Protocol):
    async def list_documents(self, **kwargs) -> list[RemoteDocument]:
        """소스에서 사용 가능한 문서 목록을 반환합니다."""
        ...

    async def download(self, document_id: str) -> bytes:
        """ID로 문서를 다운로드합니다."""
        ...

    async def get_metadata(self, document_id: str) -> dict:
        """문서 메타데이터를 가져옵니다."""
        ...
```

### 커스텀 커넥터 만들기

```python
class MyConnector:
    async def list_documents(self, **kwargs):
        # RemoteDocument 목록 반환
        ...

    async def download(self, document_id):
        # bytes 반환
        ...

    async def get_metadata(self, document_id):
        # 메타데이터 딕셔너리 반환
        ...
```

플러그인 시스템으로 등록:

```python
class MyConnectorPlugin:
    name = "my-connector"
    version = "1.0.0"

    def initialize(self, config):
        self.connector = MyConnector(**config)

    def cleanup(self):
        pass

    @hookimpl
    def register_connectors(self, registry):
        registry.register_connector("my-source", self.connector)
```
