"""Chunker framework for document splitting."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from quantumrag.core.logging import get_logger
from quantumrag.core.models import Chunk, Document

logger = get_logger(__name__)


@runtime_checkable
class Chunker(Protocol):
    """Protocol for document chunkers."""

    def chunk(self, document: Document) -> list[Chunk]:
        """Split a document into chunks.

        Args:
            document: Document to split.

        Returns:
            List of Chunk instances.
        """
        ...


class ChunkerRegistry:
    """Registry mapping document types/strategies to chunker instances.

    Usage:
        registry = ChunkerRegistry()
        registry.register("fixed", FixedSizeChunker())
        registry.register("structural", StructuralChunker())
        chunker = registry.get_chunker("fixed")
    """

    def __init__(self) -> None:
        self._chunkers: dict[str, Chunker] = {}

    def register(self, strategy: str, chunker: Chunker) -> None:
        """Register a chunker for a strategy name.

        Args:
            strategy: Strategy name (e.g., "fixed", "semantic", "structural").
            chunker: Chunker instance.
        """
        self._chunkers[strategy.lower()] = chunker
        logger.debug("registered_chunker", strategy=strategy, chunker=type(chunker).__name__)

    def get_chunker(self, strategy: str) -> Chunker:
        """Get chunker by strategy name.

        Args:
            strategy: Strategy name.

        Returns:
            Matching Chunker instance.

        Raises:
            KeyError: If no chunker is registered for the strategy.
        """
        strategy_lower = strategy.lower()
        if strategy_lower not in self._chunkers:
            available = ", ".join(sorted(self._chunkers.keys()))
            raise KeyError(
                f"No chunker registered for strategy '{strategy}'. Available: {available}"
            )
        return self._chunkers[strategy_lower]

    @property
    def available_strategies(self) -> list[str]:
        """Return all registered strategy names."""
        return sorted(self._chunkers.keys())

    def has_strategy(self, strategy: str) -> bool:
        """Check if a strategy is registered."""
        return strategy.lower() in self._chunkers
