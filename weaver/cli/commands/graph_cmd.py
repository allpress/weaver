"""`weaver graph` — build + inspect + export."""
from __future__ import annotations

import json

import click

from weaver import paths
from weaver.config import load_global
from weaver.graph.builder import build_context_graph
from weaver.graph.export import export_graphml, load_json


@click.group(help="Code knowledge graph")
def group() -> None:
    pass


@group.command("build")
@click.option("--context", "context_name", required=True)
def build(context_name: str) -> None:
    cfg = load_global()
    stats = build_context_graph(context_name, max_file_bytes=cfg.graph_max_file_bytes)
    click.echo(f"nodes={stats.nodes} edges={stats.edges} "
               f"scanned={stats.files_scanned} skipped={stats.files_skipped}")


@group.command("stats")
@click.option("--context", "context_name", required=True)
def stats(context_name: str) -> None:
    snap = paths.context_graph_dir(context_name) / "snapshots" / "latest.json"
    if not snap.exists():
        raise click.ClickException("no graph snapshot — run: weaver graph build")
    g = load_json(snap)
    click.echo(f"nodes: {g.number_of_nodes()}")
    click.echo(f"edges: {g.number_of_edges()}")
    kinds: dict[str, int] = {}
    for _, data in g.nodes(data=True):
        k = str(data.get("kind", "?"))
        kinds[k] = kinds.get(k, 0) + 1
    for k, v in sorted(kinds.items()):
        click.echo(f"  {k}: {v}")


@group.command("export")
@click.option("--context", "context_name", required=True)
@click.option("--format", "fmt", type=click.Choice(["json", "graphml"]), default="graphml")
@click.option("--out", required=True)
def export(context_name: str, fmt: str, out: str) -> None:
    snap = paths.context_graph_dir(context_name) / "snapshots" / "latest.json"
    if not snap.exists():
        raise click.ClickException("no graph snapshot — run: weaver graph build")
    g = load_json(snap)
    from pathlib import Path
    out_path = Path(out)
    if fmt == "graphml":
        export_graphml(g, out_path)
    else:
        out_path.write_text(json.dumps({"nodes": list(g.nodes(data=True)),
                                        "edges": list(g.edges(data=True))}, default=str, indent=2))
    click.echo(f"wrote {out_path}")
