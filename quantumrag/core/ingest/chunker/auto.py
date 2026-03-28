"""Auto chunking strategy selection based on document type."""

from __future__ import annotations

import re
from typing import Any

from quantumrag.core.ingest.chunker.fixed import FixedSizeChunker
from quantumrag.core.ingest.chunker.semantic import SemanticChunker
from quantumrag.core.ingest.chunker.structural import StructuralChunker
from quantumrag.core.logging import get_logger
from quantumrag.core.models import Chunk, Document

logger = get_logger(__name__)

# Markdown heading pattern
_MD_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)

# HTML heading pattern
_HTML_HEADING = re.compile(r"<h[1-6][^>]*>", re.IGNORECASE)


class AutoChunker:
    """Automatically selects the best chunking strategy for a document.

    Strategy selection logic:
    - If content has Markdown headings or HTML headings -> structural
    - If content has clear paragraph structure -> semantic
    - Otherwise -> fixed-size

    The strategy can be overridden via the ``override`` parameter.

    Args:
        chunk_size: Target chunk size in words.
        overlap: Overlap words for fixed chunking.
        override: Force a specific strategy ("fixed", "semantic", "structural").
    """

    def __init__(
        self,
        chunk_size: int = 512,
        overlap: int = 50,
        override: str | None = None,
    ) -> None:
        self._chunk_size = chunk_size
        self._overlap = overlap
        self._override = override

        self._fixed = FixedSizeChunker(chunk_size=chunk_size, overlap=overlap)
        self._semantic = SemanticChunker(
            min_chunk_size=max(chunk_size // 4, 50),
            max_chunk_size=chunk_size * 2,
        )
        self._structural = StructuralChunker(
            max_chunk_size=chunk_size * 2,
            sub_chunk_size=chunk_size,
            sub_chunk_overlap=overlap,
        )

    def chunk(
        self,
        document: Document,
        document_profile: Any | None = None,
    ) -> list[Chunk]:
        """Split document using the best detected strategy.

        Args:
            document: Document to split.
            document_profile: Optional DocumentProfile for strategy guidance.

        Returns:
            List of Chunk instances with signal metadata.
        """
        # Use profile recommendation if available and no override
        strategy = self._override
        if not strategy and document_profile is not None:
            strategy = getattr(document_profile, "recommended_chunking", None)
        if not strategy or strategy == "auto":
            strategy = self._detect_strategy(document)

        logger.debug(
            "auto_chunker_strategy",
            doc_id=document.id,
            strategy=strategy,
        )

        if strategy == "structural":
            chunks = self._structural.chunk(document)
        elif strategy == "semantic":
            chunks = self._semantic.chunk(document)
        else:
            chunks = self._fixed.chunk(document)

        # Emit chunk signals
        try:
            from quantumrag.core.pipeline.signals import emit_chunk_signals

            chunks = emit_chunk_signals(chunks, document_profile=document_profile)
        except Exception as e:
            logger.debug("chunk_signal_emission_skipped", error=str(e))

        return chunks

    def _detect_strategy(self, document: Document) -> str:
        """Detect the best chunking strategy for a document."""
        content = document.content
        doc_format = document.metadata.custom.get("format", "")

        # Check for Markdown or HTML headings
        if _MD_HEADING.search(content) or _HTML_HEADING.search(content):
            return "structural"

        # Check document format hints
        if doc_format in ("markdown", "html"):
            return "structural"

        # Check for paragraph structure (multiple double-newline breaks)
        paragraph_breaks = content.count("\n\n")
        if paragraph_breaks >= 3:
            return "semantic"

        # Default to fixed
        return "fixed"

    def detect_strategy(self, document: Document) -> str:
        """Public method to detect strategy without chunking.

        Useful for testing and inspection.
        """
        return self._override or self._detect_strategy(document)
