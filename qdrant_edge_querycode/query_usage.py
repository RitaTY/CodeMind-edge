
from __future__ import annotations

from qdrant_edge_querycode import Embedder_working, store
from qdrant_edge_querycode.config import TOP_K_DEFAULT


def search(query: str, top_k: int = TOP_K_DEFAULT) -> list[dict]:
    """
    Semantic search over the indexed codebase.

    Steps:
      1. Embed the natural-language query using the same model used for indexing
      2. Query Qdrant Edge for top-k nearest neighbours (cosine similarity)
      3. Return results with score + full payload

    Returns a list of:
      {
        "score":   float,
        "payload": {file, name, language, code, summary, start_line, end_line}
      }
    """
    vec     = Embedder_working.embed_query(query)
    results = store.search(vec, top_k=top_k)
    return results
