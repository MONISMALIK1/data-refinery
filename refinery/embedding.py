"""Local, dependency-free text embeddings.

A hashed bag-of-words vector: each token is hashed into one of
EMBEDDING_DIM buckets and the vector is L2-normalised. Deterministic, no
model download, runs identically in CI -- and honest about what it is: a
lexical retriever. Swapping in a neural embedding model means replacing
these two functions and nothing else.
"""
from __future__ import annotations

import hashlib
import math
import re

from .config import EMBEDDING_DIM


def embed(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    vector = [0.0] * dim
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        bucket = int(hashlib.md5(token.encode()).hexdigest(), 16) % dim
        vector[bucket] += 1.0
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm else vector


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))
