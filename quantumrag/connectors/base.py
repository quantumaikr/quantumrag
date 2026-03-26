"""Connector base protocol for data source integrations."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from quantumrag.core.models import Document


@runtime_checkable
class Connector(Protocol):
    """Protocol for data source connectors.

    Connectors provide a unified interface to fetch documents from
    various sources (local files, URLs, cloud storage, etc.).
    """

    def connect(self) -> None:
        """Establish connection to the data source.

        Raises:
            ConnectorError: If connection fails.
        """
        ...

    def list_sources(self) -> list[str]:
        """List available source identifiers.

        Returns:
            List of source IDs (file paths, URLs, etc.).
        """
        ...

    def fetch(self, source_id: str) -> Document:
        """Fetch and parse a single source into a Document.

        Args:
            source_id: Identifier for the source to fetch.

        Returns:
            Parsed Document.

        Raises:
            ConnectorError: If fetching or parsing fails.
        """
        ...
