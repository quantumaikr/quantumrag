"""Korean encoding detection and conversion utilities."""

from __future__ import annotations

from quantumrag.core.logging import get_logger

logger = get_logger(__name__)

# Common Korean encodings in detection priority order
_KOREAN_ENCODINGS = ["utf-8", "euc-kr", "cp949", "utf-16le", "utf-16be"]


def detect_encoding(data: bytes) -> str:
    """Detect the encoding of byte data, with Korean encoding awareness.

    Detection strategy:
    1. Check for BOM (byte order marks)
    2. Try UTF-8 (most common modern encoding)
    3. Try charset-normalizer or chardet if available
    4. Try Korean-specific encodings (EUC-KR, CP949)
    5. Default to UTF-8

    Args:
        data: Raw bytes to detect encoding for.

    Returns:
        Detected encoding name (lowercase).
    """
    if not data:
        return "utf-8"

    # Check BOM
    if data[:3] == b"\xef\xbb\xbf":
        return "utf-8"
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return "utf-16"

    # Try UTF-8
    try:
        data.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass

    # Try charset-normalizer
    try:
        from charset_normalizer import from_bytes

        result = from_bytes(data).best()
        if result is not None and result.encoding:
            return result.encoding.lower()
    except ImportError:
        pass

    # Try chardet
    try:
        import chardet

        detected = chardet.detect(data)
        encoding = detected.get("encoding")
        if encoding:
            return encoding.lower()
    except ImportError:
        pass

    # Try Korean encodings
    for enc in ("euc-kr", "cp949"):
        try:
            data.decode(enc)
            return enc
        except (UnicodeDecodeError, LookupError):
            pass

    return "utf-8"


def convert_encoding(data: bytes, target: str = "utf-8") -> str:
    """Convert byte data to a target encoding string.

    Detects the source encoding automatically and converts to the target.

    Args:
        data: Raw bytes to convert.
        target: Target encoding (default: "utf-8").

    Returns:
        Decoded string in the target encoding.
    """
    if not data:
        return ""

    source_encoding = detect_encoding(data)

    try:
        text = data.decode(source_encoding)
    except (UnicodeDecodeError, LookupError):
        # Fallback: try each Korean encoding
        for enc in _KOREAN_ENCODINGS:
            try:
                text = data.decode(enc)
                logger.debug(
                    "encoding_fallback",
                    source=source_encoding,
                    fallback=enc,
                )
                break
            except (UnicodeDecodeError, LookupError):
                continue
        else:
            # Last resort
            text = data.decode("latin-1")
            logger.warning("encoding_last_resort", encoding="latin-1")

    # If target is not UTF-8, re-encode and decode
    if target.lower().replace("-", "") != "utf8":
        try:
            return text.encode(target).decode(target)
        except (UnicodeEncodeError, LookupError):
            logger.warning("target_encoding_failed", target=target)

    return text
