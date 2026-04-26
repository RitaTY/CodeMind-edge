
from __future__ import annotations

import numpy as np
from fastembed import TextEmbedding

from qdrant_edge_querycode.config import EMBED_MODEL, EMBED_CACHE_DIR, VECTOR_DIM

_model: TextEmbedding | None = None

def _get_model() -> TextEmbedding:
    global _model
    if _model is None:
        _model = TextEmbedding(
            model_name=EMBED_MODEL,
            cache_dir=EMBED_CACHE_DIR,
        )
    return _model

def _build_text(chunk: dict) -> str:
    """Combine chunk metadata into a single string for embedding."""
    parts = [
        chunk.get("name", ""),
        chunk.get("summary", ""),
        chunk.get("code", "")[:500],
        chunk.get("file", ""),
    ]
    return "\n".join(p for p in parts if p)

def embed_chunks(chunks: list[dict]) -> list[np.ndarray]:
    """
    Embed a list of code chunks.
    Returns a list of numpy arrays, one per chunk (shape: [VECTOR_DIM]).
    """
    model  = _get_model()
    texts  = [_build_text(c) for c in chunks]
    return list(model.embed(texts))

def embed_query(query: str) -> list[float]:
    """Embed a single user query string. Returns a plain Python list."""
    model  = _get_model()
    result = list(model.embed([query]))
    return result[0].tolist()
