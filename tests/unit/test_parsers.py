"""Tests for document parsers and parser registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from quantumrag.core.errors import ParseError
from quantumrag.core.ingest.parser.base import ParserRegistry
from quantumrag.core.ingest.parser.text import (
    CSVParser,
    HTMLParser,
    MarkdownParser,
    PlainTextParser,
    strip_html_tags,
)
from quantumrag.core.ingest.quality import QualityChecker
from quantumrag.core.models import Document, DocumentMetadata

# --- Fixtures ---


@pytest.fixture()
def tmp_text_file(tmp_path: Path) -> Path:
    p = tmp_path / "sample.txt"
    p.write_text("Hello, world!\nThis is a test file.", encoding="utf-8")
    return p


@pytest.fixture()
def tmp_markdown_file(tmp_path: Path) -> Path:
    p = tmp_path / "sample.md"
    p.write_text(
        "---\ntitle: My Document\nauthor: Test Author\ntags: test\n---\n\n# Heading\n\nBody text here.",
        encoding="utf-8",
    )
    return p


@pytest.fixture()
def tmp_markdown_no_frontmatter(tmp_path: Path) -> Path:
    p = tmp_path / "no_front.md"
    p.write_text("# Just a heading\n\nSome content.", encoding="utf-8")
    return p


@pytest.fixture()
def tmp_html_file(tmp_path: Path) -> Path:
    p = tmp_path / "page.html"
    p.write_text(
        "<html><head><title>Test Page</title></head>"
        "<body><h1>Welcome</h1><p>Hello world.</p>"
        "<script>var x = 1;</script></body></html>",
        encoding="utf-8",
    )
    return p


@pytest.fixture()
def tmp_csv_file(tmp_path: Path) -> Path:
    p = tmp_path / "data.csv"
    p.write_text("Name,Age,City\nAlice,30,Seoul\nBob,25,Busan\n", encoding="utf-8")
    return p


# --- PlainTextParser ---


class TestPlainTextParser:
    def test_parse_basic(self, tmp_text_file: Path) -> None:
        parser = PlainTextParser()
        doc = parser.parse(tmp_text_file)
        assert "Hello, world!" in doc.content
        assert "This is a test file." in doc.content
        assert doc.metadata.title == "sample"

    def test_parse_nonexistent_file(self, tmp_path: Path) -> None:
        parser = PlainTextParser()
        with pytest.raises(ParseError):
            parser.parse(tmp_path / "nonexistent.txt")

    def test_supported_extensions(self) -> None:
        parser = PlainTextParser()
        assert ".txt" in parser.supported_extensions
        assert ".log" in parser.supported_extensions

    def test_parse_empty_file(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.txt"
        p.write_text("", encoding="utf-8")
        parser = PlainTextParser()
        doc = parser.parse(p)
        assert doc.content == ""

    def test_raw_bytes_preserved(self, tmp_text_file: Path) -> None:
        parser = PlainTextParser()
        doc = parser.parse(tmp_text_file)
        assert doc.raw_bytes is not None
        assert b"Hello" in doc.raw_bytes


# --- MarkdownParser ---


class TestMarkdownParser:
    def test_parse_with_frontmatter(self, tmp_markdown_file: Path) -> None:
        parser = MarkdownParser()
        doc = parser.parse(tmp_markdown_file)
        assert doc.metadata.title == "My Document"
        assert doc.metadata.author == "Test Author"
        assert "# Heading" in doc.content
        assert "Body text here." in doc.content

    def test_frontmatter_custom_fields(self, tmp_markdown_file: Path) -> None:
        parser = MarkdownParser()
        doc = parser.parse(tmp_markdown_file)
        assert doc.metadata.custom.get("tags") == "test"

    def test_parse_without_frontmatter(self, tmp_markdown_no_frontmatter: Path) -> None:
        parser = MarkdownParser()
        doc = parser.parse(tmp_markdown_no_frontmatter)
        assert doc.metadata.title == "no_front"
        assert "# Just a heading" in doc.content

    def test_supported_extensions(self) -> None:
        parser = MarkdownParser()
        assert ".md" in parser.supported_extensions
        assert ".markdown" in parser.supported_extensions


# --- HTMLParser ---


class TestHTMLParser:
    def test_parse_html(self, tmp_html_file: Path) -> None:
        parser = HTMLParser()
        doc = parser.parse(tmp_html_file)
        assert doc.metadata.title == "Test Page"
        assert "Welcome" in doc.content
        assert "Hello world." in doc.content
        # Script content should be stripped
        assert "var x = 1" not in doc.content

    def test_strip_html_tags(self) -> None:
        html = "<p>Hello <b>world</b></p><script>evil()</script>"
        clean = strip_html_tags(html)
        assert "Hello" in clean
        assert "world" in clean
        assert "evil" not in clean
        assert "<p>" not in clean

    def test_html_entities(self) -> None:
        html = "<p>Price: &lt;$10 &amp; free</p>"
        clean = strip_html_tags(html)
        assert "<$10" in clean
        assert "& free" in clean


# --- CSVParser ---


class TestCSVParser:
    def test_parse_csv(self, tmp_csv_file: Path) -> None:
        parser = CSVParser()
        doc = parser.parse(tmp_csv_file)
        assert "Name" in doc.content
        assert "Alice" in doc.content
        assert "Seoul" in doc.content
        assert doc.metadata.custom.get("row_count") == "2"
        assert doc.metadata.custom.get("column_count") == "3"

    def test_parse_empty_csv(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.csv"
        p.write_text("", encoding="utf-8")
        parser = CSVParser()
        doc = parser.parse(p)
        assert doc.content == ""

    def test_supported_extensions(self) -> None:
        parser = CSVParser()
        assert ".csv" in parser.supported_extensions
        assert ".tsv" in parser.supported_extensions


# --- ParserRegistry ---


class TestParserRegistry:
    def test_register_and_get(self) -> None:
        registry = ParserRegistry()
        parser = PlainTextParser()
        registry.register(parser)
        retrieved = registry.get_parser("file.txt")
        assert isinstance(retrieved, PlainTextParser)

    def test_get_parser_by_extension(self) -> None:
        registry = ParserRegistry()
        registry.register(PlainTextParser())
        registry.register(MarkdownParser())
        assert isinstance(registry.get_parser("doc.txt"), PlainTextParser)
        assert isinstance(registry.get_parser("doc.md"), MarkdownParser)

    def test_get_parser_unknown_extension(self) -> None:
        registry = ParserRegistry()
        registry.register(PlainTextParser())
        with pytest.raises(ParseError, match="No parser registered"):
            registry.get_parser("file.xyz")

    def test_supported_extensions(self) -> None:
        registry = ParserRegistry()
        registry.register(PlainTextParser())
        registry.register(CSVParser())
        exts = registry.supported_extensions
        assert ".txt" in exts
        assert ".csv" in exts

    def test_has_parser(self) -> None:
        registry = ParserRegistry()
        registry.register(PlainTextParser())
        assert registry.has_parser(".txt") is True
        assert registry.has_parser(".pdf") is False

    def test_case_insensitive(self) -> None:
        registry = ParserRegistry()
        registry.register(PlainTextParser())
        # Extensions are case-insensitive
        assert registry.has_parser(".TXT") is True

    def test_register_with_mime_types(self) -> None:
        registry = ParserRegistry()
        registry.register(HTMLParser(), mime_types=["text/html"])
        assert registry.has_parser(".html") is True


# --- QualityChecker ---


class TestQualityChecker:
    def test_good_quality(self) -> None:
        checker = QualityChecker()
        doc = Document(content="This is a well-formed document with substantial content. " * 10)
        score = checker.check(doc)
        assert score > 0.7
        assert doc.metadata.quality_score == score

    def test_empty_content(self) -> None:
        checker = QualityChecker()
        doc = Document(content="")
        score = checker.check(doc)
        assert score == 0.0

    def test_short_content(self) -> None:
        checker = QualityChecker()
        doc = Document(content="Hi")
        score = checker.check(doc)
        assert 0.0 < score < 0.8

    def test_broken_encoding(self) -> None:
        checker = QualityChecker()
        # Content with replacement characters indicating encoding errors
        doc = Document(content="Normal text \ufffd\ufffd\ufffd more \ufffd text " * 20)
        score = checker.check(doc)
        assert score < 0.9

    def test_highly_repetitive(self) -> None:
        checker = QualityChecker()
        doc = Document(content=("Same line repeated.\n" * 200))
        score = checker.check(doc)
        assert score < 0.9

    def test_whitespace_heavy(self) -> None:
        checker = QualityChecker()
        doc = Document(content="word " + "   " * 100 + " another")
        score = checker.check(doc)
        assert 0.0 < score < 1.0

    def test_score_stored_in_metadata(self) -> None:
        checker = QualityChecker()
        doc = Document(
            content="A reasonable document.",
            metadata=DocumentMetadata(quality_score=0.0),
        )
        checker.check(doc)
        assert doc.metadata.quality_score > 0.0
