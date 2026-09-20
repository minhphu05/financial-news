"""Deterministic, sentence-preferred chunking of normalized Silver content."""

import hashlib
import re


_SENTENCE_END = re.compile(r"[.!?](?=\s|$)")


class ArticleChunker:
    def __init__(self, size: int, overlap: int):
        if size < 50 or overlap < 0 or overlap >= size:
            raise ValueError("size must be >= 50 and 0 <= overlap < size")
        self.size = size
        self.overlap = overlap
        self.version = f"sentence-v1-{size}-{overlap}"

    def split(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []
        chunks: list[str] = []
        start = 0
        while start < len(text):
            hard_end = min(len(text), start + self.size)
            end = hard_end
            if hard_end < len(text):
                minimum = start + self.size // 2
                sentence_ends = [start + match.end() for match in _SENTENCE_END.finditer(text[start:hard_end])]
                preferred = [candidate for candidate in sentence_ends if candidate >= minimum]
                if preferred:
                    end = preferred[-1]
                else:
                    space = text.rfind(" ", minimum, hard_end + 1)
                    if space > start:
                        end = space
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(text):
                break
            desired = max(start + 1, end - self.overlap)
            if desired < end and desired > 0 and not text[desired - 1].isspace():
                preceding_space = text.rfind(" ", start + 1, desired + 1)
                if preceding_space >= start + 1:
                    desired = preceding_space + 1
            while desired < len(text) and text[desired].isspace():
                desired += 1
            start = desired if desired > start else end
        return chunks

    def chunk_id(self, article_id: str, content_hash: str, index: int) -> str:
        identity = f"{article_id}\n{content_hash}\n{self.version}\n{index}"
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def chunks_for_article(self, article: dict) -> list[dict]:
        source_text = article["content"]
        parts = self.split(source_text)
        version = f"{article['processing_version']}+{self.version}"
        return [{
            "chunk_id": self.chunk_id(article["article_id"], article["content_hash"], index),
            "article_id": article["article_id"],
            "chunk_index": index,
            "text": part,
            "title": article["title"],
            "source": article["source"],
            "source_url": article["source_url"],
            "published_at": article.get("published_at"),
            "stock_symbols": article.get("stock_symbols") or [],
            "entities": article.get("entities"),
            "processing_version": version,
            "content_hash": article["content_hash"],
            "source_ingestion_id": article["source_ingestion_id"],
            "chunker_version": self.version,
            "enrichment_status": article.get("enrichment_status", "unavailable"),
            "enricher_version": article.get("enricher_version"),
        } for index, part in enumerate(parts)]
