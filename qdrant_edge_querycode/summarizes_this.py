
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qdrant_edge_querycode.config import SUMMARY_CACHE
from qdrant_edge_querycode.Llm_azure import summarize_chunk

def _load_cache() -> dict[str, str]:
    path = Path(SUMMARY_CACHE)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}

def _save_cache(cache: dict[str, str]) -> None:
    Path(SUMMARY_CACHE).write_text(
        json.dumps(cache, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

def add_summaries(
    chunks: list[dict[str, Any]],
    *,
    show_progress: bool = True,
) -> list[dict[str, Any]]:
    """
    Mutate each chunk in-place by adding a "summary" field.

    Cached summaries are returned instantly.
    New summaries are generated via the LLM and written to cache.

    Returns the (mutated) chunks list for convenience.
    """
    cache   = _load_cache()
    changed = False

    if show_progress:
        try:
            from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn
            ctx: Any = Progress(
                SpinnerColumn(),
                TextColumn("[bold cyan]Summarising[/] [green]{task.fields[name]}"),
                BarColumn(),
                MofNCompleteColumn(),
            )
        except ImportError:
            ctx = None
    else:
        ctx = None

    def _process(chunk: dict) -> None:
        nonlocal changed
        cid = chunk["id"]
        if cid in cache:
            chunk["summary"] = cache[cid]
            return

        summary = summarize_chunk(chunk)
        chunk["summary"] = summary
        cache[cid]       = summary
        changed          = True

    if ctx is not None:
        with ctx as progress:
            task = progress.add_task("summarising", total=len(chunks), name="")
            for chunk in chunks:
                progress.update(task, name=chunk["name"])
                _process(chunk)
                progress.advance(task)
    else:
        for chunk in chunks:
            _process(chunk)

    if changed:
        _save_cache(cache)

    return chunks
