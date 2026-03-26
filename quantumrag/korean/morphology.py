"""Korean morphological analysis and tokenization."""

from __future__ import annotations

import re

from quantumrag.core.logging import get_logger

logger = get_logger(__name__)

# Korean Unicode range: Hangul Syllables (AC00-D7A3)
_KOREAN_CHAR = re.compile(r"[\uac00-\ud7a3]")

# Split on whitespace and punctuation, keeping Korean and English tokens
_BASIC_TOKEN_PATTERN = re.compile(r"[\uac00-\ud7a3]+|[a-zA-Z]+|[0-9]+", re.UNICODE)


class KoreanTokenizer:
    """Korean text tokenizer.

    Tries Kiwi (Korean Intelligent Word Identifier) first for high-quality
    morphological analysis. Falls back to basic regex-based splitting if
    Kiwi is not installed.

    Handles Korean-English mixed text by tokenizing each script appropriately.
    """

    def __init__(self) -> None:
        self._kiwi: object | None = None
        self._use_kiwi = False
        self._init_kiwi()

    def _init_kiwi(self) -> None:
        """Try to initialize Kiwi tokenizer."""
        try:
            from kiwipiepy import Kiwi

            self._kiwi = Kiwi()
            self._use_kiwi = True
            logger.debug("kiwi_tokenizer_initialized")
        except ImportError:
            logger.debug("kiwi_not_available_using_regex_fallback")
            self._use_kiwi = False

    def tokenize(self, text: str) -> list[str]:
        """Tokenize text into tokens.

        For Korean text, performs morphological analysis when Kiwi is available.
        For English text or when Kiwi is unavailable, uses word-level splitting.

        Args:
            text: Input text (Korean, English, or mixed).

        Returns:
            List of token strings.
        """
        if not text or not text.strip():
            return []

        if self._use_kiwi and self._kiwi is not None:
            return self._tokenize_kiwi(text)
        return self._tokenize_regex(text)

    def _tokenize_kiwi(self, text: str) -> list[str]:
        """Tokenize using Kiwi morphological analyzer."""
        try:
            result = self._kiwi.tokenize(text)  # type: ignore[union-attr]
            tokens: list[str] = []
            for token in result:
                form = token.form if hasattr(token, "form") else str(token[0])
                if form.strip():
                    tokens.append(form)
            return tokens
        except Exception as e:
            logger.warning("kiwi_tokenize_error", error=str(e))
            return self._tokenize_regex(text)

    def _tokenize_regex(self, text: str) -> list[str]:
        """Fallback regex-based tokenization for Korean-English mixed text."""
        return _BASIC_TOKEN_PATTERN.findall(text)

    @property
    def backend(self) -> str:
        """Return the active tokenizer backend name."""
        return "kiwi" if self._use_kiwi else "regex"

    def has_korean(self, text: str) -> bool:
        """Check if text contains Korean characters."""
        return bool(_KOREAN_CHAR.search(text))
