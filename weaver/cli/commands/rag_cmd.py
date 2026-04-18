"""`weaver rag` — query + reindex."""
from __future__ import annotations

import json

import click

from weaver.graph.rag_bridge import bridged_query
from weaver.rag.engine import RAGEngine
from weaver.rag.indexers import index_context


@click.group(help="RAG query + index management")
def group() -> None:
    pass


@group.command("query")
@click.argument("question", nargs=-1, required=True)
@click.option("--context", "context_name", required=True)
@click.option("--top-k", default=8)
@click.option("--bridge/--no-bridge", default=True,
              help="Reweight results by graph centrality")
@click.option("--json", "as_json", is_flag=True)
def query(question: tuple[str, ...], context_name: str, top_k: int,
          bridge: bool, as_json: bool) -> None:
    q = " ".join(question)
    if bridge:
        hits = bridged_query(context_name, q, top_k=top_k)
        payload = [{
            "id": h.rag.id,
            "score": h.combined,
            "graph_score": h.graph_score,
            "path": h.rag.metadata.get("path"),
            "repo": h.rag.metadata.get("repo"),
            "content": h.rag.content[:400],
        } for h in hits]
    else:
        engine = RAGEngine(context_name)
        hits = []
        for col in engine.list_collections():
            if col.startswith("docs__"):
                hits.extend(engine.query(col, q, top_k=top_k))
        hits.sort(key=lambda h: h.score)
        payload = [{
            "id": h.id, "score": h.score,
            "path": h.metadata.get("path"),
            "repo": h.metadata.get("repo"),
            "content": h.content[:400],
        } for h in hits[:top_k]]

    if as_json:
        click.echo(json.dumps(payload, indent=2))
    else:
        for hit in payload:
            click.echo(f"[{hit['score']:.3f}] {hit['repo']}/{hit['path']}")
            click.echo(f"  {hit['content'][:200]}…")
            click.echo()


@group.command("reindex")
@click.option("--context", "context_name", required=True)
def reindex(context_name: str) -> None:
    stats = index_context(context_name)
    click.echo(f"scanned={stats.files_scanned} indexed={stats.files_indexed} "
               f"chunks={stats.chunks_written} skipped={stats.skipped}")
