"""Text cleaning utilities for raw CafeF articles.

The cleaner normalises whitespace, drops boilerplate phrases that appear in
CafeF's body text, and runs lightweight Vietnamese-friendly Unicode
normalisation. It is deliberately conservative so that named entities are
not altered before chunking/embedding.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional

from src.rag.utils import get_logger

logger = get_logger(__name__)


# Patterns matching CafeF footer/boilerplate snippets we want to strip.
_BOILERPLATE_PATTERNS: List[re.Pattern] = [
    re.compile(r"theo\s+(cafef|cafe\s*f|nhịp sống.*)", re.IGNORECASE),
    re.compile(r"nguồn\s*:\s*cafe\s*f.*", re.IGNORECASE),
    re.compile(r"theo\s+nhịp sống.*", re.IGNORECASE),
    re.compile(r"đọc thêm.*", re.IGNORECASE),
]

# Collapse runs of whitespace, fix common stuck-together pattern ``word123word``.
_MULTI_WS_RE = re.compile(r"[ \t\u00a0]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")
_STUCK_DIGIT_LETTER_RE = re.compile(r"(?<=[a-zA-Zà-ỹÀ-Ỹ])(\d)")
_STUCK_LETTER_DIGIT_RE = re.compile(r"(?<=\d)([a-zA-Zà-ỹÀ-Ỹ])")


class TextCleaner:
    """Normalise raw article bodies into clean, indexable text.

    Parameters
    ----------
    strip_boilerplate : bool
        Whether to drop common CafeF footer snippets. Defaults to ``True``.
    """

    def __init__(self, strip_boilerplate: bool = True) -> None:
        self._strip_boilerplate = strip_boilerplate

    def clean_text(self, text: str) -> str:
        """Return a normalised version of ``text``.

        The pipeline performs:

        1. Unicode NFC normalisation (Vietnamese diacritics).
        2. Whitespace collapsing.
        3. Splitting digits stuck to letters (``"0,5%/nămcho" → "0,5%/năm cho"``).
        4. Stripping CafeF boilerplate footer (optional).

        Parameters
        ----------
        text : str
            Raw text.

        Returns
        -------
        str
            Cleaned text.
        """
        if not text:
            return ""

        text = unicodedata.normalize("NFC", text)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = _STUCK_DIGIT_LETTER_RE.sub(r" \1", text)
        text = _STUCK_LETTER_DIGIT_RE.sub(r" \1", text)
        text = _MULTI_WS_RE.sub(" ", text)
        text = _MULTI_NL_RE.sub("\n\n", text)

        if self._strip_boilerplate:
            for pat in _BOILERPLATE_PATTERNS:
                text = pat.sub("", text)

        return text.strip()

    def clean_article(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """Build a cleaned-article document ready for MongoDB persistence.

        Parameters
        ----------
        article : dict
            Raw article from the scraper. Must contain ``link`` and ``context``.

        Returns
        -------
        dict
            New document carrying the original metadata plus ``clean_text``.
        """
        link = article.get("link") or article.get("url")
        if not link:
            raise ValueError("Article is missing both 'link' and 'url'.")

        raw_body: Optional[str] = (
            article.get("context")
            or article.get("body")
            or article.get("content")
        )
        clean_text = self.clean_text(raw_body or "")

        return {
            "link": link,
            "title": article.get("title"),
            "post_date": article.get("post_date"),
            "summary": article.get("summary"),
            "ticker_symbol": article.get("ticker_symbol") or article.get("ticket_symbol"),
            "ticker_name": article.get("ticker_name") or article.get("ticket_name"),
            "keyword": article.get("keyword") or article.get("scraped_keyword"),
            "source": article.get("source", "cafef.vn"),
            "clean_text": clean_text,
            "char_count": len(clean_text),
        }
