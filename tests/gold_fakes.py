"""Deterministic vectors for tests only; these are not semantic embeddings."""

import hashlib
import math
import re
from typing import Sequence


class DeterministicTestEmbeddingProvider:
    model_id = "test-token-hash-v1"

    def __init__(self, dimension: int = 32):
        self.dimension = dimension

    def _vector(self, text: str) -> list[float]:
        values = [0.0] * self.dimension
        for token in re.findall(r"\w+", text.casefold()):
            digest = hashlib.sha256(token.encode()).digest()
            values[int.from_bytes(digest[:4], "big") % self.dimension] += 1.0
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)
