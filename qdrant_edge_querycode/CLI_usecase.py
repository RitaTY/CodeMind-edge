
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich import box

from qdrant_edge_querycode import query_usage as query_module
from qdrant_edge_querycode import store, Llm_azure as llm
from qdrant_edge_querycode.config import TOP_K_DEFAULT

app     = typer.Typer(
    name="qdrant-edge-querycode",
    help="[bold cyan]Qdrant Edge QueryCode[/] — semantic memory for your codebase, powered by Qdrant Edge.",
    rich_markup_mode="rich",
    add_completion=False,
)
console = Console()


@app.command()
def index(
    path: Path = typer.Argument(
        ...,
        help="Path to the repository you want to index.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    summarise: bool = typer.Option(
        True, "--summarise/--no-summarise",
        help="Generate LLM summaries per chunk (improves retrieval quality, recommended).",
    ),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Drop existing index and re-index from scratch.",
    ),
):
    """
    [bold]Index a repository.[/]

    Parses the codebase into chunks, generates embeddings, and stores them
    in a local Qdrant Edge shard (no server required).
    """
    console.print(
        Panel.fit(
            "[bold cyan]Qdrant Edge QueryCode Indexer[/]\n"
            f"Repo: [green]{path}[/]\n"
            f"Summarise: [yellow]{summarise}[/]  |  Force: [yellow]{force}[/]",
            border_style="cyan",
        )
    )

    from qdrant_edge_querycode.indexer import index_repo
    total = index_repo(path, summarise=summarise, force=force)

    if total > 0:
        console.print(
            f"\n[dim]Run [bold]querycode ask \"<your question>\"[/] to query this index.[/]\n"
        )

@app.command()
def ask(
    question: str = typer.Argument(..., help="Natural language question about your codebase."),
    top_k: int = typer.Option(
        TOP_K_DEFAULT, "--top-k", "-k",
        help="Number of code snippets to retrieve.",
    ),
    no_llm: bool = typer.Option(
        False, "--no-llm",
        help="Skip LLM reasoning — just show raw retrieval results.",
    ),
):
    """
    [bold]Ask a question about your indexed codebase.[/]

    Example:
        querycode ask "where is retry logic implemented?"
        querycode ask "how does authentication work?"
    """
    console.print(
        Panel.fit(
            f"[bold cyan] Query:[/] {question}",
            border_style="cyan",
        )
    )

    with console.status("[cyan]Searching codebase…[/]"):
        try:
            results = query_module.search(question, top_k=top_k)
        except Exception as e:
            console.print(f"[red]Search failed:[/] {e}")
            raise typer.Exit(1)

    if not results:
        console.print("[yellow]No results found. Have you run `querycode index`?[/]")
        raise typer.Exit(1)

    console.print(f"\n[bold] Top {len(results)} Matches[/]\n")

    table = Table(box=box.ROUNDED, border_style="dim", show_header=True, header_style="bold cyan")
    table.add_column("#",       style="dim",    width=3, justify="right")
    table.add_column("Score",   style="green",  width=7)
    table.add_column("File",    style="cyan",   no_wrap=False)
    table.add_column("Function", style="bold", no_wrap=True)
    table.add_column("Summary", style="white")

    for i, r in enumerate(results, 1):
        p = r["payload"]
        table.add_row(
            str(i),
            f"{r['score']:.3f}",
            f"{p.get('file','?')}:{p.get('start_line','?')}",
            p.get("name", "?"),
            p.get("summary", "") or "[dim]N/A[/]",
        )

    console.print(table)

    top = results[0]["payload"]
    console.print(f"\n[bold] Top Match — [cyan]{top.get('file','?')}[/][/]")
    syntax = Syntax(
        top.get("code", ""),
        top.get("language", "python"),
        theme="monokai",
        line_numbers=True,
        start_line=top.get("start_line", 1),
    )
    console.print(Panel(syntax, border_style="dim"))

    if not no_llm:
        console.print("\n[bold] LLM Explanation[/]")
        with console.status("[cyan]Thinking…[/]"):
            explanation = llm.answer_query(question, results)

        console.print(
            Panel(
                Text(explanation),
                title="[bold green]Answer[/]",
                border_style="green",
                padding=(1, 2),
            )
        )

@app.command()
def info():
    """Show statistics about the current index."""
    n = store.count()
    store.close_shard()
    console.print(
        Panel.fit(
            f"[bold cyan]Qdrant Edge QueryCode Index Stats[/]\n\n"
            f"  Indexed chunks : [bold green]{n}[/]\n"
            f"  Storage        : [cyan].qdrant-edge/[/] (local disk)\n"
            f"  Embedding model: [yellow]BAAI/bge-small-en-v1.5[/] (384 dims)\n"
            f"  LLM            : [yellow]gpt-5.4-mini via Azure OpenAI[/]",
            border_style="cyan",
        )
    )



def main():
    app()


if __name__ == "__main__":
    main()
