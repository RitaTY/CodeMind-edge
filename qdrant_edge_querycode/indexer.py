
from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from qdrant_edge_querycode import parser, Embedder_working, store, summarizes_this

console = Console()

_BATCH = 64   


def index_repo(
    repo_path: str | Path,
    *,
    summarise: bool = True,
    force: bool = False,
) -> int:
    """
    Index a repository at *repo_path*.

    Args:
        repo_path  — path to the repository root
        summarise  — if True, generate LLM summaries (improves retrieval)
        force      — if True, drop existing index and re-index from scratch

    Returns:
        Number of chunks indexed.
    """
    repo_path = Path(repo_path).resolve()

    if not repo_path.exists():
        raise FileNotFoundError(f"Repo path does not exist: {repo_path}")

    if force:
        console.print("[yellow]⚠  Dropping existing index…[/]")
        store.drop_shard()

    console.print(f"\n[bold] Scanning[/] [cyan]{repo_path}[/]…")
    all_chunks = list(parser.iter_chunks(repo_path))

    if not all_chunks:
        console.print("[red]No code chunks found. Is this a code repository?[/]")
        return 0

    console.print(f"   [green]✓[/] Found [bold]{len(all_chunks)}[/] code chunks")

    if summarise:
        console.print("\n[bold] Generating summaries[/] (cached — skips already seen chunks)…")
        summarizes_this.add_summaries(all_chunks, show_progress=True)
        console.print(f"   [green]✓[/] Summaries ready")
    else:

        for c in all_chunks:
            c.setdefault("summary", "")

    console.print(f"\n[bold] Embedding & storing[/] in Qdrant Edge…")
    total = len(all_chunks)
    stored = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Indexing chunks", total=total)

        for i in range(0, total, _BATCH):
            batch   = all_chunks[i : i + _BATCH]
            vectors = Embedder_working.embed_chunks(batch)
            vecs    = [v.tolist() for v in vectors]
            store.upsert_points(batch, vecs)
            stored += len(batch)
            progress.advance(task, len(batch))


    console.print("\n[bold] Optimising index…[/]")
    store.optimize()
    store.close_shard()

    console.print(
        f"\n[bold green] Done![/]  "
        f"[bold]{stored}[/] chunks indexed from "
        f"[cyan]{repo_path.name}[/]\n"
    )
    return stored
