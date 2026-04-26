
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from qdrant_edge import (
    Distance,
    EdgeConfig,
    EdgeShard,
    EdgeVectorParams,
    Point,
    Query,
    QueryRequest,
    UpdateOperation,
)

from qdrant_edge_querycode.config import SHARD_DIR, VECTOR_NAME, VECTOR_DIM

_shard: EdgeShard | None = None

def _build_config() -> EdgeConfig:
    return EdgeConfig(
        vectors={
            VECTOR_NAME: EdgeVectorParams(
                size=VECTOR_DIM,
                distance=Distance.Cosine,
            )
        }
    )

def get_shard() -> EdgeShard:
    """Return the global EdgeShard, creating or loading it as needed."""
    global _shard
    if _shard is not None:
        return _shard

    shard_path = Path(SHARD_DIR)
    shard_path.mkdir(parents=True, exist_ok=True)


    has_data = any(shard_path.iterdir()) if shard_path.exists() else False

    if has_data:
        _shard = EdgeShard.load(str(shard_path))
    else:
        _shard = EdgeShard.create(str(shard_path), _build_config())

    return _shard

def close_shard() -> None:
    """Flush and close the shard cleanly."""
    global _shard
    if _shard is not None:
        _shard.close()
        _shard = None

def drop_shard() -> None:
    """Delete all data — used for --force re-index."""
    import shutil
    close_shard()
    shard_path = Path(SHARD_DIR)
    if shard_path.exists():
        shutil.rmtree(shard_path)

def upsert_points(chunks: list[dict], vectors: list[list[float]]) -> None:
    """
    Insert or update points in the Edge Shard.

    Each point stores the full chunk payload so we can display results
    without having to re-read source files.
    """
    shard  = get_shard()
    points = []

    for chunk, vec in zip(chunks, vectors):
        payload = {
            "file":       chunk["file"],
            "name":       chunk["name"],
            "kind":       chunk.get("kind", "function"),
            "language":   chunk["language"],
            "code":       chunk["code"],
            "summary":    chunk.get("summary", ""),
            "start_line": chunk.get("start_line", 1),
            "end_line":   chunk.get("end_line", 1),
        }
        # Qdrant Edge accepts hex string IDs
        points.append(
            Point(
                id=chunk["id"],
                vector={VECTOR_NAME: vec},
                payload=payload,
            )
        )


    shard.update(UpdateOperation.upsert_points(points))

def optimize() -> None:
    """Run optimizer — merge segments and build HNSW index."""
    get_shard().optimize()

def count() -> int:
    """Return number of indexed code chunks."""
    try:
        return get_shard().count()
    except Exception:
        return 0

def search(query_vector: list[float], top_k: int = 5) -> list[dict[str, Any]]:
    """
    Similarity search against the Edge Shard.

    Returns a list of dicts with:
      { "score": float, "payload": dict }
    """
    shard = get_shard()

    results = shard.query(
        QueryRequest(
            query=Query.Nearest(query_vector, using=VECTOR_NAME),
            limit=top_k,
            with_vector=False,
            with_payload=True,
        )
    )

    output = []
    for r in results:
        output.append({
            "score":   round(r.score, 4),
            "payload": dict(r.payload) if r.payload else {},
        })

    return output
