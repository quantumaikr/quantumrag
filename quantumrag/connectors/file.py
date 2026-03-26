"""File system connector for local directory ingestion."""

from __future__ import annotations

from pathlib import Path

from quantumrag.core.errors import ConnectorError, ParseError
from quantumrag.core.ingest.parser.base import ParserRegistry, create_default_registry
from quantumrag.core.logging import get_logger
from quantumrag.core.models import Document

logger = get_logger(__name__)


class FileConnector:
    """Connector that scans local directories and parses files.

    Usage:
        connector = FileConnector("/path/to/docs")
        connector.connect()
        sources = connector.list_sources()
        for source_id in sources:
            doc = connector.fetch(source_id)
    """

    def __init__(
        self,
        root_dir: str | Path,
        recursive: bool = True,
        registry: ParserRegistry | None = None,
    ) -> None:
        """Initialize the file connector.

        Args:
            root_dir: Root directory to scan for files.
            recursive: Whether to scan subdirectories recursively.
            registry: Optional ParserRegistry. Uses default if not provided.
        """
        self._root_dir = Path(root_dir)
        self._recursive = recursive
        self._registry = registry or create_default_registry()
        self._sources: list[str] = []

    def connect(self) -> None:
        """Verify the root directory exists and scan for supported files."""
        if not self._root_dir.exists():
            raise ConnectorError(
                f"Directory not found: {self._root_dir}",
                source=str(self._root_dir),
            )
        if not self._root_dir.is_dir():
            raise ConnectorError(
                f"Not a directory: {self._root_dir}",
                source=str(self._root_dir),
            )

        self._sources = self._scan_files()
        logger.info(
            "file_connector_connected",
            root_dir=str(self._root_dir),
            file_count=len(self._sources),
        )

    def list_sources(self) -> list[str]:
        """List all discovered file paths."""
        return list(self._sources)

    def fetch(self, source_id: str) -> Document:
        """Parse a file using the appropriate parser.

        Args:
            source_id: File path (absolute or relative to root_dir).

        Returns:
            Parsed Document.

        Raises:
            ConnectorError: If parsing fails.
        """
        file_path = Path(source_id)
        if not file_path.is_absolute():
            file_path = self._root_dir / file_path

        try:
            parser = self._registry.get_parser(file_path)
            return parser.parse(file_path)
        except ParseError as e:
            raise ConnectorError(
                f"Failed to parse file: {e}",
                source=str(file_path),
            ) from e

    def _scan_files(self) -> list[str]:
        """Scan directory for files with supported extensions."""
        supported_exts = set(self._registry.supported_extensions)
        files: list[str] = []

        if self._recursive:
            iterator = self._root_dir.rglob("*")
        else:
            iterator = self._root_dir.glob("*")

        for path in sorted(iterator):
            if path.is_file() and path.suffix.lower() in supported_exts:
                files.append(str(path))

        return files
