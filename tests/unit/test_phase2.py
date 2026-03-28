"""Tests for Phase 2: Sprints 12-15."""

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

# ──────────────────────────────────────────────
# Sprint 13: Connector base models
# ──────────────────────────────────────────────


class TestConnectorModels:
    """Test connector data models."""

    def test_connector_document_fields(self):
        from quantumrag.connectors.gdrive import ConnectorDocument

        doc = ConnectorDocument(
            id="abc123",
            name="test.pdf",
            path="/docs/test.pdf",
            modified_at=datetime(2025, 1, 1),
            size=1024,
            mime_type="application/pdf",
        )
        assert doc.id == "abc123"
        assert doc.name == "test.pdf"
        assert doc.size == 1024

    def test_sync_result_defaults(self):
        from quantumrag.connectors.gdrive import SyncResult

        result = SyncResult()
        assert result.added == 0
        assert result.updated == 0
        assert result.deleted == 0
        assert result.errors == []

    def test_sync_result_with_values(self):
        from quantumrag.connectors.gdrive import SyncResult

        result = SyncResult(added=5, updated=2, deleted=1, errors=["err1"])
        assert result.added == 5
        assert result.errors == ["err1"]

    def test_gdrive_connector_init(self):
        from quantumrag.connectors.gdrive import GoogleDriveConnector

        conn = GoogleDriveConnector(credentials_path="/tmp/creds.json", folder_id="folder1")
        assert conn._credentials_path == "/tmp/creds.json"
        assert conn._folder_id == "folder1"

    def test_notion_connector_init(self):
        from quantumrag.connectors.notion import NotionConnector

        conn = NotionConnector(api_key="secret-key", database_id="db123")
        assert conn._api_key == "secret-key"
        assert conn._database_id == "db123"

    def test_s3_connector_init(self):
        from quantumrag.connectors.s3 import S3Connector

        conn = S3Connector(bucket="my-bucket", prefix="docs/")
        assert conn._bucket == "my-bucket"
        assert conn._prefix == "docs/"

    def test_s3_guess_mime(self):
        from quantumrag.connectors.s3 import _guess_mime

        assert _guess_mime("file.pdf") == "application/pdf"
        assert _guess_mime("file.txt") == "text/plain"
        assert _guess_mime("file.xyz") == "application/octet-stream"


# ──────────────────────────────────────────────
# Sprint 14: ACL Filtering
# ──────────────────────────────────────────────


class TestACLFilter:
    """Test access control list filtering."""

    def _make(self):
        from quantumrag.core.security.acl import ACLFilter

        return ACLFilter()

    def test_no_identity_returns_all(self):
        acl = self._make()
        results = [{"metadata": {"acl_roles": ["admin"]}}, {"metadata": {}}]
        filtered = acl.apply(results)
        assert len(filtered) == 2

    def test_public_documents_always_accessible(self):
        acl = self._make()
        results = [{"metadata": {}}, {"metadata": {"title": "public"}}]
        filtered = acl.apply(results, user_roles=["viewer"], user_id="user1")
        assert len(filtered) == 2

    def test_role_based_filtering(self):
        acl = self._make()
        results = [
            {"metadata": {"acl_roles": ["admin", "engineering"]}},
            {"metadata": {"acl_roles": ["finance"]}},
            {"metadata": {}},  # public
        ]
        filtered = acl.apply(results, user_roles=["engineering"])
        assert len(filtered) == 2  # engineering doc + public doc

    def test_user_id_filtering(self):
        acl = self._make()
        results = [
            {"metadata": {"acl_users": ["alice", "bob"]}},
            {"metadata": {"acl_users": ["charlie"]}},
            {"metadata": {}},  # public
        ]
        filtered = acl.apply(results, user_id="alice")
        assert len(filtered) == 2  # alice's doc + public

    def test_combined_role_and_user(self):
        acl = self._make()
        results = [
            {"metadata": {"acl_roles": ["admin"], "acl_users": ["alice"]}},
            {"metadata": {"acl_roles": ["engineering"]}},
        ]
        # Alice with engineering role can access both
        filtered = acl.apply(results, user_roles=["engineering"], user_id="alice")
        assert len(filtered) == 2

    def test_no_access(self):
        acl = self._make()
        results = [
            {"metadata": {"acl_roles": ["admin"]}},
            {"metadata": {"acl_users": ["bob"]}},
        ]
        filtered = acl.apply(results, user_roles=["viewer"], user_id="alice")
        assert len(filtered) == 0

    def test_create_acl_metadata(self):
        from quantumrag.core.security.acl import ACLFilter

        meta = ACLFilter.create_acl_metadata(
            roles=["admin", "engineering"],
            users=["alice"],
        )
        assert meta["acl_roles"] == ["admin", "engineering"]
        assert meta["acl_users"] == ["alice"]

    def test_create_acl_metadata_empty(self):
        from quantumrag.core.security.acl import ACLFilter

        meta = ACLFilter.create_acl_metadata()
        assert meta == {}

    def test_works_with_object_metadata(self):
        """ACL filter should work with objects that have a .metadata attribute."""
        acl = self._make()

        @dataclass
        class FakeResult:
            metadata: dict = field(default_factory=dict)

        results = [
            FakeResult(metadata={"acl_roles": ["admin"]}),
            FakeResult(metadata={}),
        ]
        filtered = acl.apply(results, user_roles=["admin"])
        assert len(filtered) == 2


# ──────────────────────────────────────────────
# Sprint 15: IncrementalIndexer
# ──────────────────────────────────────────────


class TestIncrementalIndexer:
    """Test incremental change detection and application."""

    def _make_store(self, docs=None):
        store = AsyncMock()
        store.list_documents = AsyncMock(return_value=docs or [])
        store.delete_document = AsyncMock(return_value=True)
        return store

    def _make_indexer_mock(self):
        indexer = AsyncMock()
        indexer.ingest_file = AsyncMock()
        return indexer

    def test_detect_new_files(self):
        """Files on disk but not in store should be detected as added."""
        from quantumrag.core.ingest.indexer.incremental import IncrementalIndexer

        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            (p / "new_doc.txt").write_text("hello world")
            (p / "another.pdf").write_bytes(b"PDF content")
            (p / "ignore.xyz").write_text("not indexed")  # unsupported extension

            store = self._make_store(docs=[])
            idx = IncrementalIndexer(document_store=store)
            changes = asyncio.run(idx.detect_changes(p))

            assert len(changes.added) == 2  # .txt and .pdf, not .xyz
            names = {c.name for c in changes.added}
            assert "new_doc.txt" in names
            assert "another.pdf" in names
            assert "ignore.xyz" not in names

    def test_detect_deleted_documents(self):
        """Documents in store but not on disk should be detected as deleted."""
        from quantumrag.core.ingest.indexer.incremental import IncrementalIndexer

        @dataclass
        class FakeDoc:
            id: str = "doc1"
            metadata: Any = None

        @dataclass
        class FakeMeta:
            source_id: str = "/nonexistent/file.txt"
            custom: dict = field(default_factory=dict)

        fake_doc = FakeDoc(id="doc1", metadata=FakeMeta(source_id="/nonexistent/file.txt"))

        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            # No files on disk

            store = self._make_store(docs=[fake_doc])
            idx = IncrementalIndexer(document_store=store)
            changes = asyncio.run(idx.detect_changes(p))

            assert len(changes.deleted) == 1
            assert changes.deleted[0] == "doc1"

    def test_detect_modified_files(self):
        """Files with different hashes should be detected as modified."""
        from quantumrag.core.ingest.indexer.incremental import IncrementalIndexer

        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            file_path = p / "doc.txt"
            file_path.write_text("updated content")

            # Store has same file but with old hash
            @dataclass
            class FakeDoc:
                id: str = "doc1"
                metadata: Any = None

            @dataclass
            class FakeMeta:
                source_id: str = ""
                custom: dict = field(default_factory=dict)

            fake_doc = FakeDoc(
                id="doc1",
                metadata=FakeMeta(
                    source_id=str(file_path),
                    custom={"content_hash": "old_hash_value"},
                ),
            )

            store = self._make_store(docs=[fake_doc])
            idx = IncrementalIndexer(document_store=store)
            changes = asyncio.run(idx.detect_changes(p))

            assert len(changes.modified) == 1
            assert changes.modified[0] == file_path

    def test_no_changes_detected(self):
        """Matching hashes should result in no changes."""
        from quantumrag.core.ingest.indexer.incremental import IncrementalIndexer, _file_hash

        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            file_path = p / "doc.txt"
            file_path.write_text("same content")
            correct_hash = _file_hash(file_path)

            @dataclass
            class FakeDoc:
                id: str = "doc1"
                metadata: Any = None

            @dataclass
            class FakeMeta:
                source_id: str = ""
                custom: dict = field(default_factory=dict)

            fake_doc = FakeDoc(
                id="doc1",
                metadata=FakeMeta(
                    source_id=str(file_path),
                    custom={"content_hash": correct_hash},
                ),
            )

            store = self._make_store(docs=[fake_doc])
            idx = IncrementalIndexer(document_store=store)
            changes = asyncio.run(idx.detect_changes(p))

            assert changes.is_empty

    def test_apply_changes(self):
        """Apply changes should call indexer and store appropriately."""
        from quantumrag.core.ingest.indexer.incremental import ChangeSet, IncrementalIndexer

        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            new_file = p / "new.txt"
            new_file.write_text("new content")

            changes = ChangeSet(
                added=[new_file],
                modified=[],
                deleted=["old_doc_id"],
            )

            store = self._make_store()
            indexer_mock = self._make_indexer_mock()
            idx = IncrementalIndexer(document_store=store)

            result = asyncio.run(idx.apply_changes(changes, indexer_mock))

            assert result.added == 1
            assert result.deleted == 1
            assert result.elapsed_seconds > 0
            indexer_mock.ingest_file.assert_called_once()
            store.delete_document.assert_called_once_with("old_doc_id")

    def test_changeset_properties(self):
        from quantumrag.core.ingest.indexer.incremental import ChangeSet

        cs = ChangeSet(added=[Path("a.txt")], modified=[], deleted=["d1"])
        assert cs.total_changes == 2
        assert not cs.is_empty

        empty = ChangeSet()
        assert empty.total_changes == 0
        assert empty.is_empty

    def test_file_hash_consistency(self):
        from quantumrag.core.ingest.indexer.incremental import _file_hash

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test content for hashing")
            f.flush()
            path = Path(f.name)

        h1 = _file_hash(path)
        h2 = _file_hash(path)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex digest length
        path.unlink()
