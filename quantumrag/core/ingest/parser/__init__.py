"""Document parsers for various file formats."""

from quantumrag.core.ingest.parser.base import (
    Parser,
    ParserRegistry,
    create_default_registry,
)
from quantumrag.core.ingest.parser.text import (
    CSVParser,
    HTMLParser,
    MarkdownParser,
    PlainTextParser,
)

__all__ = [
    "CSVParser",
    "HTMLParser",
    "MarkdownParser",
    "Parser",
    "ParserRegistry",
    "PlainTextParser",
    "create_default_registry",
]
