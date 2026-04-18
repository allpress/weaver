"""Embedding backends: sentence-transformers default, pluggable later."""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


_MODEL_CACHE: dict[str, Any] = {}


def embed_texts(texts: list[str], *, model: str = "all-MiniLM-L6-v2") -> list[list[float]]:
    """Embed a batch of strings. Caches the model across calls."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        raise RuntimeError(
            "sentence-transformers required for embeddings. "
            "pip install sentence-transformers"
        ) from e

    m = _MODEL_CACHE.get(model)
    if m is None:
        log.info("loading embedding model: %s", model)
        m = SentenceTransformer(model)
        _MODEL_CACHE[model] = m

    vecs = m.encode(texts, show_progress_bar=False, normalize_embeddings=True)
    return [v.tolist() for v in vecs]
