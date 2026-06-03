"""Sentence-aware recursive text chunker for Vietnamese financial news.

The chunker splits text recursively on a hierarchy of separators
(paragraph → sentence → clause → word) and merges small pieces into
chunks of approximately ``chunk_size`` characters with word-boundary–safe
overlap. This avoids cutting Vietnamese words mid-syllable.
"""

from __future__ import annotations

import re
from typing import List, Optional

from src.rag.config import Settings, get_settings


_DEFAULT_SEPARATORS: List[str] = ["\n\n", "\n", ". ", "? ", "! ", ", ", " ", ""]

# Regex to find the last word boundary within the overlap region.
_WORD_BOUNDARY_RE = re.compile(r"\s+")


class TextChunker:
    """Recursive character splitter tuned for Vietnamese financial news.

    Uses sentence-level separators first so that chunks align with natural
    sentence boundaries. Overlap is snapped to the nearest word boundary to
    prevent mid-word truncation (e.g. ``"rước"`` cut from ``"trước"``).

    Parameters
    ----------
    settings : Optional[Settings]
        Settings override. Defaults to :func:`get_settings`.
    separators : Optional[List[str]]
        Separators used in order. Each separator is tried before falling
        back to the next, finer-grained one.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        separators: Optional[List[str]] = None,
    ) -> None:
        cfg = (settings or get_settings()).chunking
        self._chunk_size = cfg.chunk_size
        self._chunk_overlap = cfg.chunk_overlap
        self._min_chunk_chars = cfg.min_chunk_chars
        self._separators = separators or _DEFAULT_SEPARATORS

        if self._chunk_overlap >= self._chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size.")

    def split(self, text: str) -> List[str]:
        """Split ``text`` into overlapping chunks.

        Parameters
        ----------
        text : str
            Cleaned text.

        Returns
        -------
        list[str]
            Chunks no longer than ``chunk_size``, all containing at least
            ``min_chunk_chars`` characters.
        """
        if not text:
            return []

        pieces = self._recursive_split(text, self._separators)
        merged = self._merge(pieces)
        return [c.strip() for c in merged if len(c.strip()) >= self._min_chunk_chars]

    # -- internals ----------------------------------------------------------
    def _recursive_split(self, text: str, separators: List[str]) -> List[str]:
        """Recursively split ``text`` using the first usable separator.

        The separator is re-appended to each piece (except the last) so that
        sentence-ending punctuation is preserved. For example, splitting on
        ``". "`` keeps the period attached to the preceding sentence.
        """
        if len(text) <= self._chunk_size:
            return [text]

        separator = separators[0] if separators else ""
        remaining = separators[1:] if len(separators) > 1 else []

        if separator == "":
            return [text[i : i + self._chunk_size] for i in range(0, len(text), self._chunk_size)]

        raw_splits = text.split(separator) if separator else list(text)

        # Re-attach separator to each piece (except last) to preserve
        # sentence boundaries: "Câu 1. Câu 2" → ["Câu 1.", "Câu 2"]
        splits: List[str] = []
        for i, piece in enumerate(raw_splits):
            if i < len(raw_splits) - 1 and separator.strip():
                splits.append(piece + separator.rstrip())
            else:
                splits.append(piece)

        out: List[str] = []
        for chunk in splits:
            if len(chunk) <= self._chunk_size:
                out.append(chunk)
            else:
                out.extend(self._recursive_split(chunk, remaining))
        return out

    def _merge(self, pieces: List[str]) -> List[str]:
        """Merge small pieces into ``chunk_size``-bounded windows.

        Each piece (from the recursive split) typically corresponds to a
        sentence or paragraph. The merger accumulates pieces in a buffer
        and flushes when adding the next piece would exceed the chunk size.
        This guarantees that chunk boundaries fall between sentences rather
        than mid-sentence.

        Overlap between consecutive chunks is snapped to the nearest
        whitespace boundary so that no Vietnamese word is split mid-syllable.
        """
        chunks: List[str] = []
        buffer: List[str] = []
        buffer_len = 0

        # Separator inserted between merged pieces for readability.
        sep = " "
        sep_len = len(sep)

        def flush() -> None:
            nonlocal buffer, buffer_len
            if buffer:
                chunks.append(sep.join(buffer))
                buffer, buffer_len = [], 0

        for piece in pieces:
            piece = piece.strip()
            if not piece:
                continue
            piece_len = len(piece)
            # Space between existing buffer and new piece.
            needed = piece_len + (sep_len if buffer else 0)

            if buffer_len + needed <= self._chunk_size:
                buffer.append(piece)
                buffer_len += needed
                continue

            # Flush the current buffer (ends at a sentence boundary).
            flush()
            if piece_len > self._chunk_size:
                # Piece still too large — slide window as fallback.
                start = 0
                step = self._chunk_size - self._chunk_overlap
                while start < piece_len:
                    chunks.append(piece[start : start + self._chunk_size])
                    start += step
            else:
                buffer.append(piece)
                buffer_len = piece_len

        flush()

        if self._chunk_overlap > 0 and len(chunks) > 1:
            overlapped: List[str] = [chunks[0]]
            for prev, curr in zip(chunks, chunks[1:]):
                tail = self._word_safe_tail(prev, self._chunk_overlap)
                combined = (tail + " " + curr).strip()
                overlapped.append(combined[: self._chunk_size])
            chunks = overlapped

        return chunks

    @staticmethod
    def _word_safe_tail(text: str, max_chars: int) -> str:
        """Extract the last ``max_chars`` of ``text``, snapped to a word start.

        Instead of slicing at an arbitrary character position (which may cut
        a Vietnamese word in half), this finds the nearest whitespace boundary
        within the overlap region and starts from the next word.

        Parameters
        ----------
        text : str
            Source text to extract tail from.
        max_chars : int
            Maximum characters to extract.

        Returns
        -------
        str
            Tail string starting at a word boundary.
        """
        if len(text) <= max_chars:
            return text
        raw_tail = text[-max_chars:]
        # Find the first whitespace in the tail and start after it
        match = _WORD_BOUNDARY_RE.search(raw_tail)
        if match:
            return raw_tail[match.end():]
        return raw_tail
