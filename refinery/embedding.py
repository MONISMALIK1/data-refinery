"""Neural text embeddings via sentence-transformers.

Uses all-MiniLM-L6-v2 (384-dim, ~80 MB, runs fully locally). The model
is lazy-loaded and cached for the process lifetime. Falls back to the
hashed bag-of-words implementation when sentence-transformers is not
installed so CI and offline use cases are unaffected.
"""
from __future__ import annotations

import hashlib
import math
import re

from .config import EMBEDDING_DIM

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def _hash_embed(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    vector = [0.0] * dim
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        bucket = int(hashlib.md5(token.encode()).hexdigest(), 16) % dim
        vector[bucket] += 1.0
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm else vector


def embed(text: str) -> list[float]:
    try:
        model = _get_model()
        return model.encode(text, normalize_embeddings=True).tolist()
    except Exception:
        return _hash_embed(text)


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))
