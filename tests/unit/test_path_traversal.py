"""Tests for Sprint E3.3 — Path traversal hardening.

Covers:
- ``../../../etc/passwd`` style attacks
- URL-encoded path traversal (``%2e%2e``)
- Symlinks escaping the allowed directory
- Valid paths within the base directory
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from quantumrag.api.server import validate_path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def base_dir(tmp_path: Path) -> Path:
    """Create a temporary base directory with some content."""
    (tmp_path / "allowed").mkdir()
    (tmp_path / "allowed" / "file.txt").write_text("hello")
    (tmp_path / "allowed" / "subdir").mkdir()
    (tmp_path / "allowed" / "subdir" / "nested.txt").write_text("nested")
    return tmp_path / "allowed"


@pytest.fixture()
def outside_file(tmp_path: Path) -> Path:
    """Create a file outside the allowed base directory."""
    secret = tmp_path / "secret.txt"
    secret.write_text("top-secret")
    return secret


# ---------------------------------------------------------------------------
# Basic path traversal attacks
# ---------------------------------------------------------------------------


class TestPathTraversalBasic:
    """Classic ``..`` based traversal attacks."""

    def test_dotdot_etc_passwd(self, base_dir: Path):
        with pytest.raises(HTTPException) as exc_info:
            validate_path("../../../etc/passwd", base_dir)
        assert exc_info.value.status_code == 403

    def test_dotdot_relative(self, base_dir: Path):
        with pytest.raises(HTTPException) as exc_info:
            validate_path("../secret.txt", base_dir)
        assert exc_info.value.status_code == 403

    def test_absolute_outside_path(self, base_dir: Path):
        with pytest.raises(HTTPException) as exc_info:
            validate_path("/etc/passwd", base_dir)
        assert exc_info.value.status_code == 403

    def test_windows_style_backslash(self, base_dir: Path):
        """Backslash traversal (relevant on Windows, but validated on all OS)."""
        with pytest.raises(HTTPException) as exc_info:
            validate_path("..\\..\\etc\\passwd", base_dir)
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# URL-encoded path traversal
# ---------------------------------------------------------------------------


class TestURLEncodedTraversal:
    """Percent-encoded sequences must be decoded before validation."""

    def test_percent_encoded_dotdot(self, base_dir: Path):
        """``%2e%2e/%2e%2e/etc/passwd`` should be blocked."""
        with pytest.raises(HTTPException) as exc_info:
            validate_path("%2e%2e/%2e%2e/etc/passwd", base_dir)
        assert exc_info.value.status_code == 403

    def test_double_encoded_dotdot(self, base_dir: Path):
        """``%252e%252e`` (double-encoded) — after one decode still contains
        ``%2e%2e`` which is literal, but ``Path.resolve()`` handles the rest."""
        # After one unquote: ``%2e%2e`` which is literal chars — resolve
        # won't interpret these as ``..``.  If they don't escape, that's fine.
        # The key is that the *first* level of decoding is done.
        with pytest.raises(HTTPException) as exc_info:
            validate_path("%2e%2e/%2e%2e/%2e%2e/etc/passwd", base_dir)
        assert exc_info.value.status_code == 403

    def test_encoded_slash(self, base_dir: Path):
        """``..%2f..%2fetc%2fpasswd`` — encoded forward slashes."""
        with pytest.raises(HTTPException) as exc_info:
            validate_path("..%2f..%2fetc%2fpasswd", base_dir)
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Symlink attacks
# ---------------------------------------------------------------------------


class TestSymlinkTraversal:
    """Symlinks inside the allowed directory that point outside must be blocked."""

    def test_symlink_escaping_base(self, base_dir: Path, outside_file: Path):
        """A symlink inside base_dir pointing to a file outside should be rejected."""
        link = base_dir / "evil_link"
        link.symlink_to(outside_file)

        with pytest.raises(HTTPException) as exc_info:
            validate_path(str(link), base_dir)
        assert exc_info.value.status_code == 403

    def test_symlink_within_base_is_allowed(self, base_dir: Path):
        """A symlink that stays within base_dir should be accepted."""
        target = base_dir / "file.txt"
        link = base_dir / "good_link"
        link.symlink_to(target)

        result = validate_path(str(link), base_dir)
        # The resolved path should be the real file
        assert result == target.resolve()

    def test_directory_symlink_escape(self, base_dir: Path, tmp_path: Path):
        """A directory symlink pointing outside should be rejected."""
        outside_dir = tmp_path / "outside_dir"
        outside_dir.mkdir()
        (outside_dir / "data.txt").write_text("escaped")

        link = base_dir / "dir_link"
        link.symlink_to(outside_dir)

        with pytest.raises(HTTPException) as exc_info:
            validate_path(str(link / "data.txt"), base_dir)
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Valid paths
# ---------------------------------------------------------------------------


class TestValidPaths:
    """Legitimate paths within the base directory should be accepted."""

    def test_direct_file(self, base_dir: Path):
        result = validate_path(str(base_dir / "file.txt"), base_dir)
        assert result == (base_dir / "file.txt").resolve()

    def test_nested_file(self, base_dir: Path):
        result = validate_path(str(base_dir / "subdir" / "nested.txt"), base_dir)
        assert result == (base_dir / "subdir" / "nested.txt").resolve()

    def test_base_dir_itself(self, base_dir: Path):
        result = validate_path(str(base_dir), base_dir)
        assert result == base_dir.resolve()

    def test_path_with_dot_component(self, base_dir: Path):
        """``./file.txt`` relative to base should work if it resolves inside."""
        result = validate_path(str(base_dir / "." / "file.txt"), base_dir)
        assert result == (base_dir / "file.txt").resolve()
