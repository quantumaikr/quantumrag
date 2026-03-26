"""Pipeline context and signal system for cross-module communication.

The pipeline module provides the signal infrastructure that enables modules
to communicate rich context to each other without tight coupling.

Key concepts:
- **PipelineContext**: A shared context object that flows through all pipeline
  stages, accumulating signals and enabling downstream stages to make better
  decisions.
- **DocumentProfile**: Document-level analysis produced at ingest time,
  describing structure, domain, language mix, and information density.
- **ChunkSignal**: Per-chunk metadata produced by chunkers, describing
  completeness, boundary type, and information type.
- **QuerySignal**: Enriched query classification with domain hints,
  intent type, and retrieval strategy recommendations.
"""

from quantumrag.core.pipeline.context import (
    ChunkSignal,
    DocumentProfile,
    InformationType,
    PipelineContext,
    QuerySignal,
    RetrievalHints,
)

__all__ = [
    "ChunkSignal",
    "DocumentProfile",
    "InformationType",
    "PipelineContext",
    "QuerySignal",
    "RetrievalHints",
]
