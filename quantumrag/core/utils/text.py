"""Shared text processing utilities.

Single source of truth for sentence splitting, tokenization,
text similarity, and language detection used across the pipeline.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Compiled patterns (module-level, compiled once)
# ---------------------------------------------------------------------------

# Sentence endings: standard punctuation + Korean verb endings
# Covers: 습니다/입니다/겠습니다/됩니다 (formal), 어요/해요/세요/나요 (polite),
#          다/죠/네/까 (plain/question), and standard . ! ? 。
_SENTENCE_SPLIT = re.compile(
    r"(?<=[.!?。])\s+"
    r"|(?<=습니다)\s+"  # 했습니다, 입니다, 됩니다, 겠습니다
    r"|(?<=어요)\s+"  # 했어요, 있어요
    r"|(?<=해요)\s+"  # 그래요, 좋아해요
    r"|(?<=세요)\s+"  # 하세요, 주세요
    r"|(?<=나요)\s+"  # 되나요, 있나요 (question)
    r"|(?<=거든요)\s+"  # 그렇거든요 (explanation)
    r"|(?<=[다요까죠네])\.\s+"  # 다. 요. 까. 죠. 네.
    r"|(?<=[다요까죠네])\s*\n"  # sentence-ending + newline (no period)
)

# Fallback sentence boundary for chunkers
_SENTENCE_END = re.compile(
    r"[.!?。]\s+|[.!?。]$"
    r"|(?<=습니다)[.)\s]"  # formal endings
    r"|(?<=[다요까죠네])[.]\s*"  # plain endings with period
)

# Word tokenization
_WORD_RE = re.compile(r"\w+")

# Korean character detection (Hangul Syllables + Jamo + Compatibility Jamo)
_KOREAN_CHAR_RE = re.compile(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]")

# Default Korean detection threshold (ratio of Korean chars to total length)
_KOREAN_THRESHOLD = 0.2

# Content detection patterns
_TABLE_MD_RE = re.compile(r"\|.*\|.*\|")
_TABLE_HTML_RE = re.compile(r"<table[\s>]", re.IGNORECASE)
_CODE_FENCE_RE = re.compile(r"```")
_CODE_INDENT_RE = re.compile(r"^\s{4,}(?:def |class |import |from |if |for )", re.MULTILINE)
_LIST_UNORDERED_RE = re.compile(r"^\s*[-*•]\s+", re.MULTILINE)
_LIST_ORDERED_RE = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)
_DIGIT_RE = re.compile(r"\d")

# Sentence completeness patterns
_SENTENCE_TERMINATOR_RE = re.compile(r"[.!?。다요]\s*$")
_MID_SENTENCE_START_RE = re.compile(
    r"^(?:and|but|or|however|또한|그러나|하지만|그리고|이에)",
    re.IGNORECASE,
)

# Legal structure
_LEGAL_CLAUSE_RE = re.compile(r"제\s*\d+\s*[조항]|Article\s+\d+", re.IGNORECASE)


# ---------------------------------------------------------------------------
# PDF / Document Text Normalization
# ---------------------------------------------------------------------------

# Unicode bidirectional control characters that pollute PDF-extracted text.
# These include LTR/RTL overrides, embeddings, and pop-formatting marks.
_BIDI_CONTROL_RE = re.compile(
    r"[\u200e\u200f"  # LRM, RLM
    r"\u202a-\u202e"  # LRE, RLE, PDF, LRO, RLO
    r"\u2066-\u2069"  # LRI, RLI, FSI, PDI
    r"\u200b-\u200d"  # ZWSP, ZWNJ, ZWJ
    r"\ufeff"  # BOM / ZWNBSP
    r"]"
)

# Line breaks that were introduced by bidi-mark removal, leaving
# orphaned newlines between words that were originally on the same line.
_ORPHAN_NEWLINE_RE = re.compile(
    r"(?<=[a-zA-Z,;:\-\u3131-\u318f\uac00-\ud7af])\n(?=[a-zA-Z\u3131-\u318f\uac00-\ud7af])"
)

# Excessive whitespace (3+ newlines → 2)
_EXCESSIVE_NEWLINE_RE = re.compile(r"\n{3,}")


def normalize_extracted_text(text: str) -> str:
    """Normalize text extracted from PDFs and other document formats.

    Removes bidi control characters, rejoins lines split by bidi marks,
    and collapses excessive whitespace. This is critical for embedding
    quality — bidi marks cause tokenizers to split words incorrectly.

    Args:
        text: Raw extracted text (may contain bidi marks, orphan newlines).

    Returns:
        Cleaned text suitable for chunking and embedding.
    """
    if not text:
        return text

    # Step 1: Strip bidi control characters
    cleaned = _BIDI_CONTROL_RE.sub("", text)

    # Step 2: Rejoin lines that were split by bidi mark removal.
    # "5,000\n image-caption" → "5,000 image-caption"
    cleaned = _ORPHAN_NEWLINE_RE.sub(" ", cleaned)

    # Step 3: Collapse excessive blank lines
    cleaned = _EXCESSIVE_NEWLINE_RE.sub("\n\n", cleaned)

    return cleaned.strip()


# ---------------------------------------------------------------------------
# Sentence Splitting
# ---------------------------------------------------------------------------


def split_sentences(text: str) -> list[str]:
    """Split text into sentences handling both English and Korean.

    Handles:
    - Standard punctuation: . ! ? 。
    - Korean verb endings: 다. 요. 니다 어요 해요 죠.
    """
    sentences = _SENTENCE_SPLIT.split(text.strip())
    return [s.strip() for s in sentences if s.strip()]


def split_sentences_with_fallback(text: str) -> list[str]:
    """Split sentences with newline fallback for unstructured text.

    Used by chunkers that need to handle text without clear
    sentence boundaries.
    """
    parts = _SENTENCE_END.split(text)
    sentences = [s.strip() for s in parts if s.strip()]

    if len(sentences) <= 1 and "\n" in text:
        sentences = [s.strip() for s in text.split("\n") if s.strip()]

    if not sentences:
        sentences = [text.strip()] if text.strip() else []

    return sentences


# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------


def tokenize(text: str) -> list[str]:
    """Simple word tokenization using word-character boundaries.

    Returns a list of lowercase tokens.
    """
    return _WORD_RE.findall(text.lower())


def tokenize_set(text: str) -> set[str]:
    """Tokenize to a set of unique lowercase words."""
    return set(_WORD_RE.findall(text.lower()))


# Stop words for relevance scoring (English-focused)
_STOP_WORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "can",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "and",
        "but",
        "or",
        "nor",
        "not",
        "so",
        "yet",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
    }
)


def tokenize_filtered(text: str) -> set[str]:
    """Tokenize with stop word removal. Returns a set.

    Used for relevance scoring where common words add noise.
    """
    words = _WORD_RE.findall(text.lower())
    return {w for w in words if w not in _STOP_WORDS and len(w) > 1}


# ---------------------------------------------------------------------------
# Text Similarity
# ---------------------------------------------------------------------------


def vocab_overlap(text_a: str, text_b: str) -> float:
    """Word-level Jaccard similarity between two texts."""
    words_a = tokenize_set(text_a)
    words_b = tokenize_set(text_b)
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def char_bigrams(text: str) -> set[str]:
    """Extract character bigrams (whitespace removed, lowercased).

    Character bigrams capture sub-word overlap, which is especially
    effective for Korean where agglutinative particles change word
    endings (e.g., "프로젝트를" vs "프로젝트가").
    """
    cleaned = re.sub(r"\s+", "", text.lower())
    if len(cleaned) < 2:
        return set()
    return {cleaned[i : i + 2] for i in range(len(cleaned) - 1)}


def text_similarity(text_a: str, text_b: str) -> float:
    """Combined word + character-bigram similarity.

    Takes the max of word-level Jaccard and bigram Jaccard,
    capturing both English (word-level) and Korean (bigram-level)
    similarity effectively.
    """
    # Word-level Jaccard
    word_sim = vocab_overlap(text_a, text_b)

    # Character-bigram Jaccard
    bi_a = char_bigrams(text_a)
    bi_b = char_bigrams(text_b)
    bigram_sim = 0.0
    if bi_a and bi_b:
        union = len(bi_a | bi_b)
        bigram_sim = len(bi_a & bi_b) / union if union > 0 else 0.0

    return max(word_sim, bigram_sim)


# ---------------------------------------------------------------------------
# Language Detection
# ---------------------------------------------------------------------------


def detect_korean(text: str, threshold: float = _KOREAN_THRESHOLD) -> bool:
    """Detect if text is primarily Korean.

    Args:
        text: Text to analyze.
        threshold: Minimum ratio of Korean characters to total length.

    Returns:
        True if Korean character ratio exceeds threshold.
    """
    if not text:
        return False
    ko_count = len(_KOREAN_CHAR_RE.findall(text))
    return ko_count > len(text) * threshold


def has_korean(text: str) -> bool:
    """Check if text contains any Korean characters (presence check)."""
    return bool(_KOREAN_CHAR_RE.search(text))


# ---------------------------------------------------------------------------
# Content Detection Helpers
# ---------------------------------------------------------------------------


def has_table(content: str) -> bool:
    """Detect tables (Markdown or HTML) in content."""
    return bool(_TABLE_MD_RE.search(content) or _TABLE_HTML_RE.search(content))


def has_code(content: str) -> bool:
    """Detect code blocks (fenced or indented) in content."""
    return bool(_CODE_FENCE_RE.search(content) or _CODE_INDENT_RE.search(content))


def has_list(content: str) -> bool:
    """Detect bullet or numbered lists in content."""
    return bool(_LIST_UNORDERED_RE.search(content) or _LIST_ORDERED_RE.search(content))


def has_legal_structure(content: str) -> bool:
    """Detect legal clause patterns (제N조, Article N)."""
    return bool(_LEGAL_CLAUSE_RE.search(content))


def numeric_density(words: list[str]) -> float:
    """Compute ratio of tokens containing digits."""
    if not words:
        return 0.0
    count = sum(1 for w in words if _DIGIT_RE.search(w))
    return round(count / len(words), 3)


def ends_with_terminator(text: str) -> bool:
    """Check if text ends with a sentence terminator."""
    return bool(_SENTENCE_TERMINATOR_RE.search(text.strip()))


def starts_mid_sentence(text: str) -> bool:
    """Check if text starts mid-sentence (conjunction or lowercase)."""
    stripped = text.strip()
    if not stripped:
        return False
    if stripped[0].islower():
        return True
    return bool(_MID_SENTENCE_START_RE.match(stripped))


# ---------------------------------------------------------------------------
# Table Block Detection (for pre-chunking table protection)
# ---------------------------------------------------------------------------

# Matches a complete markdown table block: header + separator + data rows
_TABLE_BLOCK_RE = re.compile(
    r"(?:^|\n)"  # start of line
    r"(\|[^\n]+\|\s*\n"  # header row
    r"\|[\s:|-]+\|\s*\n"  # separator row
    r"(?:\|[^\n]+\|\s*\n?)*)",  # data rows
    re.MULTILINE,
)


def split_preserving_tables(text: str) -> list[tuple[str, bool]]:
    """Split text into segments, keeping markdown tables as atomic blocks.

    Returns a list of (text_segment, is_table) tuples. Table blocks are
    never split across segments so chunkers can treat them as atomic units.
    """
    matches = list(_TABLE_BLOCK_RE.finditer(text))
    if not matches:
        return [(text, False)]

    segments: list[tuple[str, bool]] = []
    last_end = 0

    for m in matches:
        # Text before this table
        before = text[last_end : m.start()]
        if before.strip():
            segments.append((before, False))
        # The table itself
        segments.append((m.group(1).strip(), True))
        last_end = m.end()

    # Text after the last table
    after = text[last_end:]
    if after.strip():
        segments.append((after, False))

    return segments


# ---------------------------------------------------------------------------
# Code Block Detection (for pre-chunking code block protection)
# ---------------------------------------------------------------------------

# Matches a complete fenced code block: ```lang ... ```
_CODE_BLOCK_RE = re.compile(
    r"(?:^|\n)"  # start of line
    r"(```[^\n]*\n"  # opening fence (with optional language)
    r"[\s\S]*?"  # code content (non-greedy)
    r"```)\s*",  # closing fence
    re.MULTILINE,
)


def split_preserving_code_blocks(text: str) -> list[tuple[str, bool]]:
    """Split text into segments, keeping fenced code blocks as atomic blocks.

    Returns a list of (text_segment, is_code_block) tuples. Code blocks are
    never split across segments so chunkers can treat them as atomic units.
    """
    matches = list(_CODE_BLOCK_RE.finditer(text))
    if not matches:
        return [(text, False)]

    segments: list[tuple[str, bool]] = []
    last_end = 0

    for m in matches:
        # Text before this code block
        before = text[last_end : m.start()]
        if before.strip():
            segments.append((before, False))
        # The code block itself
        segments.append((m.group(1).strip(), True))
        last_end = m.end()

    # Text after the last code block
    after = text[last_end:]
    if after.strip():
        segments.append((after, False))

    return segments


# Short code blocks (≤ this many lines) are merged with adjacent text
# instead of being emitted as separate atomic chunks, so they retain
# surrounding context (e.g., section headings, explanatory prose).
_SHORT_CODE_BLOCK_LINES = 6


def split_preserving_blocks(text: str) -> list[tuple[str, str]]:
    """Split text preserving both tables and code blocks as atomic units.

    Returns a list of (text_segment, block_type) tuples where block_type
    is 'table', 'code', or 'text'.

    Short code blocks (≤ 6 lines) are kept as 'text' so they stay merged
    with their surrounding prose — this preserves section-heading context
    for snippets like a 3-line Variance example.
    """
    result: list[tuple[str, str]] = []

    # First pass: protect code blocks
    code_segments = split_preserving_code_blocks(text)

    for segment, is_code in code_segments:
        if is_code:
            # Short code blocks → merge with surrounding text
            code_lines = segment.strip().split("\n")
            # Subtract the ``` fences themselves
            content_lines = len(code_lines) - 2 if len(code_lines) > 2 else 0
            if content_lines <= _SHORT_CODE_BLOCK_LINES:
                result.append((segment, "text"))
            else:
                result.append((segment, "code"))
        else:
            # Second pass: protect tables within non-code text
            table_segments = split_preserving_tables(segment)
            for tseg, is_table in table_segments:
                if is_table:
                    result.append((tseg, "table"))
                else:
                    result.append((tseg, "text"))

    # Post-process: split large tables into sub-tables with header preserved
    final: list[tuple[str, str]] = []
    for segment, block_type in result:
        if block_type == "table":
            sub_tables = _split_large_table(segment, max_rows=15)
            for st in sub_tables:
                final.append((st, "table"))
        else:
            final.append((segment, block_type))

    return final


def _split_large_table(table_text: str, max_rows: int = 15) -> list[str]:
    """Split a large markdown table into sub-tables, preserving headers.

    Each sub-table keeps the original header row and separator,
    so retrieval can match column names in every chunk.
    """
    lines = table_text.strip().split("\n")
    table_lines = [line for line in lines if line.strip().startswith("|")]

    if len(table_lines) <= max_rows + 2:  # header + separator + max_rows
        return [table_text]

    # Extract header (row 0) and separator (row 1)
    header = table_lines[0]
    separator = table_lines[1] if len(table_lines) > 1 else ""
    data_rows = table_lines[2:]

    # Extract non-table text before the table (title, etc.)
    pre_text_lines = []
    for line in lines:
        if line.strip().startswith("|"):
            break
        pre_text_lines.append(line)
    pre_text = "\n".join(pre_text_lines).strip()

    sub_tables: list[str] = []
    for i in range(0, len(data_rows), max_rows):
        batch = data_rows[i : i + max_rows]
        parts = []
        if pre_text:
            parts.append(pre_text)
        parts.append(header)
        if separator:
            parts.append(separator)
        parts.extend(batch)
        sub_tables.append("\n".join(parts))

    return sub_tables


# ---------------------------------------------------------------------------
# Korean-Aware Token Size Estimation
# ---------------------------------------------------------------------------


def estimate_token_count(text: str) -> int:
    """Estimate token count for embedding models, aware of Korean text.

    For English, word count ≈ token count (1.3x multiplier).
    For Korean, each character can be 1-3 tokens for typical embedding
    models, and a Korean "word" (space-delimited) averages ~2-4 tokens.

    This uses a blended heuristic: word_count + (korean_char_count * 0.7).
    """
    words = text.split()
    word_count = len(words)
    ko_char_count = len(_KOREAN_CHAR_RE.findall(text))
    if ko_char_count == 0:
        return word_count
    # Korean chars contribute ~0.7 extra tokens each beyond the word count
    # (since word_count already counts Korean words, we add a supplement)
    return word_count + int(ko_char_count * 0.7)
