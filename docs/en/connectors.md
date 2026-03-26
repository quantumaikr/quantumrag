# Data Connectors

> Ingest documents from local files, cloud storage, and SaaS platforms.

---

## Overview

QuantumRAG provides connectors for various data sources. All connectors implement a common interface with async support, recursive listing, and metadata preservation.

---

## Supported Connectors

| Connector | Source | Auth |
|-----------|--------|------|
| **File** | Local filesystem | None |
| **URL** | HTTP/HTTPS URLs | None |
| **S3** | AWS S3 buckets | AWS credentials |
| **Google Drive** | Google Drive folders | OAuth2 / Service Account |
| **Notion** | Notion databases | Integration token |

---

## File Connector

Ingest from local filesystem paths.

```python
engine = Engine()
engine.ingest("./docs")                    # Directory
engine.ingest("./report.pdf")              # Single file
engine.ingest("./docs", recursive=True)    # Recursive
```

CLI:

```bash
quantumrag ingest ./docs --recursive
quantumrag ingest ./report.pdf
```

### Watch Mode

Monitor a directory for changes and auto-ingest:

```bash
quantumrag ingest ./docs --watch
```

---

## URL Connector

Ingest from web URLs.

```python
engine.ingest("https://example.com/report.pdf")
```

Supports HTTP/HTTPS with automatic format detection.

---

## S3 Connector

Ingest from AWS S3 buckets.

**Prerequisites:**
- AWS credentials configured (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
- Or IAM role with S3 read permissions

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

## Google Drive Connector

Ingest from Google Drive folders.

**Prerequisites:**
- Google Cloud project with Drive API enabled
- OAuth2 credentials or service account key

```python
from quantumrag.connectors.gdrive import GDriveConnector

connector = GDriveConnector(
    folder_id="1ABC...",
    credentials_path="credentials.json",
)

documents = await connector.list_documents()
```

---

## Notion Connector

Ingest from Notion databases and pages.

**Prerequisites:**
- Notion integration token (`NOTION_TOKEN`)
- Integration added to target database/page

```python
from quantumrag.connectors.notion import NotionConnector

connector = NotionConnector(
    database_id="abc123...",
    token="secret_...",
)

documents = await connector.list_documents()
```

---

## Connector Interface

All connectors implement the base protocol:

```python
class Connector(Protocol):
    async def list_documents(self, **kwargs) -> list[RemoteDocument]:
        """List available documents from the source."""
        ...

    async def download(self, document_id: str) -> bytes:
        """Download a document by ID."""
        ...

    async def get_metadata(self, document_id: str) -> dict:
        """Get document metadata."""
        ...
```

### Creating a Custom Connector

```python
class MyConnector:
    async def list_documents(self, **kwargs):
        # Return list of RemoteDocument
        ...

    async def download(self, document_id):
        # Return bytes
        ...

    async def get_metadata(self, document_id):
        # Return metadata dict
        ...
```

Register via the plugin system:

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
