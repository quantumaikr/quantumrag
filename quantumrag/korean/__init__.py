"""Korean language support: tokenization and encoding."""

from quantumrag.korean.encoding import convert_encoding, detect_encoding
from quantumrag.korean.morphology import KoreanTokenizer

__all__ = ["KoreanTokenizer", "convert_encoding", "detect_encoding"]
