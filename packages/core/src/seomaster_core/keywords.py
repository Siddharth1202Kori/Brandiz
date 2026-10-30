"""Keyword text normalization. Every cache key, list item and ClickHouse row uses this form."""

import unicodedata

MAX_KEYWORD_LEN = 200  # Google Ads rejects longer phrases; DataForSEO caps at 80 words


class InvalidKeywordError(ValueError):
    pass


def normalize_keyword(raw: str) -> str:
    """NFC, lowercase, trim, collapse internal whitespace. Raises on empty/too long input."""
    kw = " ".join(unicodedata.normalize("NFC", raw).casefold().split())
    if not kw:
        raise InvalidKeywordError("Keyword is empty")
    if len(kw) > MAX_KEYWORD_LEN:
        raise InvalidKeywordError(f"Keyword is longer than {MAX_KEYWORD_LEN} characters")
    return kw


def word_count(kw: str) -> int:
    return len(kw.split())
