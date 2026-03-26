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
_SENTENCE_SPLIT = re.compile(
    r"(?<=[.!?。])\s+"
    r"|(?<=[다요])\.\s+"
    r"|(?<=니다)\s+"
    r"|(?<=어요)\s+"
    r"|(?<=해요)\s+"
    r"|(?<=죠\.)\s+"
)

# Fallback sentence boundary for chunkers
_SENTENCE_END = re.compile(r"[.!?。]\s+|[.!?。]$|(?<=[다요까])[.]\s*")

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
_CODE_INDENT_RE = re.compile(
    r"^\s{4,}(?:def |class |import |from |if |for )", re.MULTILINE
)
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
_LEGAL_CLAUSE_RE = re.compile(
    r"제\s*\d+\s*[조항]|Article\s+\d+", re.IGNORECASE
)


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
_STOP_WORDS: frozenset[str] = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "and", "but", "or", "nor", "not", "so", "yet",
    "it", "its", "this", "that", "these", "those",
})


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
    return {cleaned[i: i + 2] for i in range(len(cleaned) - 1)}


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
