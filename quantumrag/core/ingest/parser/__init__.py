"""Document parsers for various file formats."""

from quantumrag.core.ingest.parser.base import (
    BenchmarkResult,
    ComparisonReport,
    Parser,
    ParserBenchmark,
    ParserRegistry,
    ParserVariant,
    create_default_registry,
    create_registry_with_variants,
)
from quantumrag.core.ingest.parser.text import (
    CSVParser,
    HTMLParser,
    MarkdownParser,
    PlainTextParser,
)

__all__ = [
    "BenchmarkResult",
    "CSVParser",
    "ComparisonReport",
    "HTMLParser",
    "MarkdownParser",
    "Parser",
    "ParserBenchmark",
    "ParserRegistry",
    "ParserVariant",
    "PlainTextParser",
    "create_default_registry",
    "create_registry_with_variants",
]
