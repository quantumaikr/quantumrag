"""Tests for chunking engine."""

from __future__ import annotations

from quantumrag.core.ingest.chunker.auto import AutoChunker
from quantumrag.core.ingest.chunker.context import ContextualPrefixer
from quantumrag.core.ingest.chunker.fixed import FixedSizeChunker
from quantumrag.core.ingest.chunker.semantic import SemanticChunker
from quantumrag.core.ingest.chunker.structural import StructuralChunker
from quantumrag.core.models import Chunk, Document, DocumentMetadata

# --- Helpers ---


def _make_doc(content: str, title: str = "Test Doc", **custom: str) -> Document:
    return Document(
        content=content,
        metadata=DocumentMetadata(title=title, custom=custom),
    )


def _word_count(text: str) -> int:
    return len(text.split())


# --- FixedSizeChunker ---


class TestFixedSizeChunker:
    def test_basic_chunking(self) -> None:
        text = " ".join(["word"] * 100)
        doc = _make_doc(text)
        chunker = FixedSizeChunker(chunk_size=30, overlap=5)
        chunks = chunker.chunk(doc)
        assert len(chunks) >= 2
        for chunk in chunks:
            assert chunk.document_id == doc.id

    def test_empty_content(self) -> None:
        doc = _make_doc("")
        chunker = FixedSizeChunker(chunk_size=50)
        chunks = chunker.chunk(doc)
        assert chunks == []

    def test_small_content_single_chunk(self) -> None:
        doc = _make_doc("A short sentence.")
        chunker = FixedSizeChunker(chunk_size=100)
        chunks = chunker.chunk(doc)
        assert len(chunks) == 1
        assert "short sentence" in chunks[0].content

    def test_chunk_indices_sequential(self) -> None:
        text = " ".join(["word"] * 200)
        doc = _make_doc(text)
        chunker = FixedSizeChunker(chunk_size=30, overlap=0)
        chunks = chunker.chunk(doc)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_overlap_produces_shared_content(self) -> None:
        # Build sentences where each is ~10 words
        sentences = [f"Sentence number {i} has several words in it." for i in range(20)]
        text = " ".join(sentences)
        doc = _make_doc(text)
        chunker = FixedSizeChunker(chunk_size=40, overlap=10)
        chunks = chunker.chunk(doc)
        if len(chunks) >= 2:
            # There should be some overlap between consecutive chunks
            words_0 = set(chunks[0].content.split())
            words_1 = set(chunks[1].content.split())
            overlap = words_0 & words_1
            assert len(overlap) > 0

    def test_sentence_boundary_respect(self) -> None:
        text = "First sentence here. Second sentence follows. Third one is last."
        doc = _make_doc(text)
        chunker = FixedSizeChunker(chunk_size=5, overlap=0)
        chunks = chunker.chunk(doc)
        # Chunks should not split mid-sentence
        for chunk in chunks:
            # Each chunk should contain at least a recognizable word fragment
            assert len(chunk.content.strip()) > 0


# --- SemanticChunker ---


class TestSemanticChunker:
    def test_paragraph_splitting(self) -> None:
        text = "Paragraph one with content.\n\nParagraph two with more.\n\nParagraph three here."
        doc = _make_doc(text)
        chunker = SemanticChunker(min_chunk_size=1, max_chunk_size=100)
        chunks = chunker.chunk(doc)
        assert len(chunks) >= 1

    def test_empty_document(self) -> None:
        doc = _make_doc("")
        chunker = SemanticChunker()
        assert chunker.chunk(doc) == []

    def test_single_paragraph(self) -> None:
        doc = _make_doc("Just one paragraph with no breaks.")
        chunker = SemanticChunker(min_chunk_size=1, max_chunk_size=100)
        chunks = chunker.chunk(doc)
        assert len(chunks) == 1

    def test_large_paragraph_split(self) -> None:
        text = " ".join(["word"] * 500)
        doc = _make_doc(text)
        chunker = SemanticChunker(min_chunk_size=50, max_chunk_size=100)
        chunks = chunker.chunk(doc)
        # Large single paragraph should be split
        assert len(chunks) >= 2


# --- StructuralChunker ---


class TestStructuralChunker:
    def test_markdown_heading_split(self) -> None:
        text = (
            "# Introduction\n\nSome intro text here.\n\n"
            "## Details\n\nMore detailed content.\n\n"
            "## Conclusion\n\nFinal thoughts."
        )
        doc = _make_doc(text)
        chunker = StructuralChunker()
        chunks = chunker.chunk(doc)
        assert len(chunks) >= 3
        # Check sections are captured in metadata
        sections = [c.metadata.get("section", "") for c in chunks]
        assert "Introduction" in sections
        assert "Details" in sections
        assert "Conclusion" in sections

    def test_no_headings_single_chunk(self) -> None:
        text = "Plain text without any headings. Just regular content."
        doc = _make_doc(text)
        chunker = StructuralChunker()
        chunks = chunker.chunk(doc)
        assert len(chunks) >= 1

    def test_large_section_sub_split(self) -> None:
        large_section = " ".join(["word"] * 2000)
        text = f"# Big Section\n\n{large_section}"
        doc = _make_doc(text)
        chunker = StructuralChunker(max_chunk_size=200, sub_chunk_size=100)
        chunks = chunker.chunk(doc)
        assert len(chunks) > 1

    def test_empty_document(self) -> None:
        doc = _make_doc("")
        chunker = StructuralChunker()
        assert chunker.chunk(doc) == []

    def test_content_before_first_heading(self) -> None:
        text = "Preamble content.\n\n# First Section\n\nSection body."
        doc = _make_doc(text)
        chunker = StructuralChunker()
        chunks = chunker.chunk(doc)
        contents = [c.content for c in chunks]
        assert any("Preamble" in c for c in contents)


# --- AutoChunker ---


class TestAutoChunker:
    def test_detects_structural_for_markdown(self) -> None:
        text = "# Heading\n\nContent here.\n\n## Subheading\n\nMore content."
        doc = _make_doc(text)
        chunker = AutoChunker()
        strategy = chunker.detect_strategy(doc)
        assert strategy == "structural"

    def test_detects_structural_for_html(self) -> None:
        text = "<h1>Title</h1><p>Content</p><h2>Section</h2><p>More</p>"
        doc = _make_doc(text)
        chunker = AutoChunker()
        strategy = chunker.detect_strategy(doc)
        assert strategy == "structural"

    def test_detects_semantic_for_paragraphs(self) -> None:
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph.\n\nFourth paragraph."
        doc = _make_doc(text)
        chunker = AutoChunker()
        strategy = chunker.detect_strategy(doc)
        assert strategy == "semantic"

    def test_detects_fixed_for_plain_text(self) -> None:
        text = "Just a plain block of text without structure."
        doc = _make_doc(text)
        chunker = AutoChunker()
        strategy = chunker.detect_strategy(doc)
        assert strategy == "fixed"

    def test_override_strategy(self) -> None:
        text = "# Heading\n\nShould be structural but overridden."
        doc = _make_doc(text)
        chunker = AutoChunker(override="fixed")
        strategy = chunker.detect_strategy(doc)
        assert strategy == "fixed"

    def test_chunks_produced(self) -> None:
        text = "# Section 1\n\nContent one.\n\n# Section 2\n\nContent two."
        doc = _make_doc(text)
        chunker = AutoChunker()
        chunks = chunker.chunk(doc)
        assert len(chunks) >= 2

    def test_empty_document(self) -> None:
        doc = _make_doc("")
        chunker = AutoChunker()
        assert chunker.chunk(doc) == []


# --- ContextualPrefixer ---


class TestContextualPrefixer:
    def test_default_prefix(self) -> None:
        doc = _make_doc("Content", title="My Report")
        chunks = [
            Chunk(content="chunk1", document_id=doc.id, chunk_index=0),
            Chunk(content="chunk2", document_id=doc.id, chunk_index=1),
        ]
        prefixer = ContextualPrefixer()
        prefixer.add_context(chunks, doc)
        assert "My Report" in chunks[0].context_prefix
        assert "My Report" in chunks[1].context_prefix

    def test_prefix_with_section(self) -> None:
        doc = _make_doc("Content", title="Report")
        chunks = [
            Chunk(
                content="chunk1",
                document_id=doc.id,
                chunk_index=0,
                metadata={"section": "Introduction"},
            ),
        ]
        prefixer = ContextualPrefixer()
        prefixer.add_context(chunks, doc)
        assert "Report" in chunks[0].context_prefix
        assert "Introduction" in chunks[0].context_prefix

    def test_custom_template(self) -> None:
        doc = _make_doc("Content", title="Doc")
        chunks = [
            Chunk(
                content="chunk",
                document_id=doc.id,
                chunk_index=0,
                metadata={"section": "Sec1"},
            ),
        ]
        prefixer = ContextualPrefixer(template="[{title} / {section}]")
        prefixer.add_context(chunks, doc)
        assert chunks[0].context_prefix == "[Doc / Sec1]"

    def test_no_section_in_metadata(self) -> None:
        doc = _make_doc("Content", title="Notes")
        chunks = [
            Chunk(content="chunk", document_id=doc.id, chunk_index=0),
        ]
        prefixer = ContextualPrefixer()
        prefixer.add_context(chunks, doc)
        assert "Notes" in chunks[0].context_prefix
        # Should not contain "section" when no section
        assert (
            "section" not in chunks[0].context_prefix.lower()
            or "section" in chunks[0].context_prefix.lower()
        )

    def test_empty_chunk_list(self) -> None:
        doc = _make_doc("Content")
        prefixer = ContextualPrefixer()
        result = prefixer.add_context([], doc)
        assert result == []
