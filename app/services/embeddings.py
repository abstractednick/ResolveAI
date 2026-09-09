"""Local embedding generation (works offline; swap for Voyage/OpenAI in prod)."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Iterable

from app.config import get_settings

settings = get_settings()


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def embed_text(text: str, dims: int | None = None) -> list[float]:
    """
    Deterministic bag-of-tokens embedding into a fixed-size vector.
    Good enough for local similarity; replace with Voyage/OpenAI embeddings in prod.
    """
    dims = dims or settings.embedding_dims
    vec = [0.0] * dims
    tokens = _tokenize(text)
    if not tokens:
        return vec
    for token in tokens:
        digest = hashlib.sha256(token.encode()).digest()
        idx = int.from_bytes(digest[:4], "big") % dims
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[idx] += sign
    # L2 normalize
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    a_list = list(a)
    b_list = list(b)
    if not a_list or not b_list or len(a_list) != len(b_list):
        return 0.0
    return sum(x * y for x, y in zip(a_list, b_list))
