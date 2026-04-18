"""`weaver context` — create, list, show, describe, delete contexts; manage recipes."""
from __future__ import annotations

import json as jsonlib

import click

from weaver import context_manager
from weaver.contexts import iter_recipes, load_manifest


@click.group(help="Manage contexts (isolated knowledge domains)")
def group() -> None:
    pass


@group.command("create")
@click.argument("name")
@click.option("--display-name", default=None)
@click.option("--description", default=None, help="One-line context description")
@click.option("--recipe", default=None,
              help="Recipe slug to instantiate (see `weaver context recipes`)")
@click.option("--kind", default="custom",
              help="Context kind tag when no recipe is used")
@click.option("--activate/--no-activate", default=False)
@click.option("--source-control-base-url", default=None, help="e.g. https://gitlab.example.com")
@click.option("--source-control-group", default=None, help="Group or owner to clone from")
def create(name: str, display_name: str | None, description: str | None,
           recipe: str | None, kind: str, activate: bool,
           source_control_base_url: str | None,
           source_control_group: str | None) -> None:
    path = context_manager.create(
        name,
        display_name=display_name,
        description=description,
        recipe=recipe,
        kind=kind,
        activate=activate,
        source_control_base_url=source_control_base_url,
        source_control_group=source_control_group,
    )
    click.echo(f"created context {name} at {path}")
    if recipe:
        click.echo(f"  from recipe: {recipe}")
        click.echo(f"  edit: {path / 'manifest.yaml'}")


@group.command("list")
@click.option("--json", "as_json", is_flag=True)
def list_contexts(as_json: bool) -> None:
    rows = context_manager.all_summaries()
    if as_json:
        click.echo(jsonlib.dumps([
            {
                "name": s.name, "display_name": s.display_name,
                "kind": s.kind, "recipe": s.recipe,
                "active": s.active, "repos": s.repos,
                "has_chromadb": s.has_chromadb, "has_graph": s.has_graph,
                "has_manifest": s.has_manifest,
            } for s in rows
        ], indent=2))
        return
    if not rows:
        click.echo("no contexts — try: weaver context create <name> --recipe ai-corpus")
        return
    for s in rows:
        active = "*" if s.active else " "
        kind_note = f"[{s.kind}]" if s.has_manifest else "[legacy]"
        click.echo(f"{active} {s.name:20} {kind_note:20} "
                   f"repos={s.repos:3}  rag={'y' if s.has_chromadb else 'n'}  "
                   f"graph={'y' if s.has_graph else 'n'}")


@group.command("show")
@click.argument("name")
def show(name: str) -> None:
    s = context_manager.summary(name)
    click.echo(f"name:         {s.name}")
    click.echo(f"display:      {s.display_name}")
    click.echo(f"kind:         {s.kind}")
    click.echo(f"recipe:       {s.recipe or '-'}")
    click.echo(f"description:  {s.description[:120] or '-'}")
    click.echo(f"active:       {s.active}")
    click.echo(f"repos:        {s.repos}")
    click.echo(f"has_manifest: {s.has_manifest}")
    click.echo(f"has_chromadb: {s.has_chromadb}")
    click.echo(f"has_graph:    {s.has_graph}")


@group.command("describe")
@click.argument("name")
def describe(name: str) -> None:
    """Full context report: manifest + cache + graph + RAG stats."""
    s = context_manager.summary(name)
    manifest = load_manifest(name)

    click.echo(f"# {s.display_name}")
    click.echo("")
    if manifest:
        click.echo(f"name:        {manifest.name}")
        click.echo(f"kind:        {manifest.kind}")
        click.echo(f"recipe:      {manifest.recipe or '-'}")
        click.echo(f"created:     {manifest.created_at.isoformat()}")
        if manifest.description:
            click.echo("")
            click.echo("description:")
            for line in manifest.description.strip().splitlines():
                click.echo(f"  {line}")
        click.echo("")
        click.echo("focus:")
        for t in manifest.focus.primary_topics:
            click.echo(f"  + {t}")
        if manifest.focus.exclude_topics:
            for t in manifest.focus.exclude_topics:
                click.echo(f"  - {t}")
        if manifest.focus.entity_types:
            click.echo(f"  entity types: {', '.join(manifest.focus.entity_types)}")
        click.echo("")
        click.echo("decay (half-lives, days):")
        click.echo(f"  news:    {manifest.decay.news_half_life_days}")
        click.echo(f"  post:    {manifest.decay.post_half_life_days}")
        click.echo(f"  concept: {manifest.decay.concept_half_life_days}")
        click.echo(f"  project: {manifest.decay.project_half_life_days}")
        click.echo(f"  person:  {'no decay' if manifest.decay.person_no_decay else 'decays'}")
    else:
        click.echo("(no manifest — legacy context)")
        click.echo("  create one with: weaver context migrate-manifest <name>")

    click.echo("")
    click.echo("state:")
    click.echo(f"  active:       {s.active}")
    click.echo(f"  repos:        {s.repos}")
    click.echo(f"  has_chromadb: {s.has_chromadb}")
    click.echo(f"  has_graph:    {s.has_graph}")

    # Aggregator cache stats
    try:
        from weaver.aggregator.cache import CacheLayout, cache_stats
        stats = cache_stats(CacheLayout(context=name))
        click.echo("")
        click.echo(f"aggregator cache: {stats['total']} items")
        for src, n in sorted(stats["per_source"].items()):
            click.echo(f"  {src:20} {n}")
    except Exception:  # noqa: BLE001
        pass

    # Graph stats (aggregator)
    try:
        from weaver.indexer.graph_writer import graph_available, graph_stats
        if graph_available():
            g = graph_stats(name)
            if g["total_nodes"]:
                click.echo("")
                click.echo(f"graph: {g['total_nodes']} nodes, {g['total_edges']} edges")
                for k, n in g["by_kind"].items():
                    click.echo(f"  {k:15} {n}")
    except Exception:  # noqa: BLE001
        pass


@group.command("recipes")
@click.option("--json", "as_json", is_flag=True)
def recipes_list(as_json: bool) -> None:
    rows = list(iter_recipes())
    if as_json:
        click.echo(jsonlib.dumps([
            {"slug": r.slug, "display_name": r.display_name,
             "kind": r.kind, "description": r.description}
            for r in rows
        ], indent=2))
        return
    if not rows:
        click.echo("(no recipes found)")
        return
    for r in rows:
        click.echo(f"{r.slug:22} [{r.kind:18}] {r.display_name}")
        if r.description:
            first_line = r.description.strip().splitlines()[0]
            click.echo(f"  {first_line[:90]}")


@group.command("show-manifest")
@click.argument("name")
def show_manifest(name: str) -> None:
    """Print the manifest.yaml path. Useful when piping into $EDITOR."""
    from weaver.contexts.manifest import manifest_path
    p = manifest_path(name)
    if not p.exists():
        raise click.ClickException(f"no manifest at {p}")
    click.echo(str(p))


@group.command("rm")
@click.argument("name")
@click.option("--force", is_flag=True, help="Actually delete")
def rm(name: str, force: bool) -> None:
    if not force:
        raise click.UsageError("refusing to delete without --force")
    context_manager.delete(name, force=True)
    click.echo(f"deleted {name}")
