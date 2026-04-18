"""`weaver clone` — the first job.

Given a GitLab base URL + group (or a saved context), clones every project
into the named context, parses docs → RAG, parses code → graph.
"""
from __future__ import annotations

import logging

import click

from weaver import context_manager, paths
from weaver.auth import AuthResolver, get_default_store
from weaver.config import load_context, load_global
from weaver.graph.builder import build_context_graph
from weaver.providers.source_control.gitlab import GitLabProvider
from weaver.rag.indexers import index_context

log = logging.getLogger(__name__)


@click.group(help="Clone source-control projects into a context + build RAG + graph")
def group() -> None:
    pass


@group.command("gitlab")
@click.option("--context", "context_name", required=True, help="Target context")
@click.option("--base-url", default=None, help="GitLab URL; falls back to context config")
@click.option("--group", "gitlab_group", default=None, help="GitLab group to clone")
@click.option("--protocol", type=click.Choice(["https", "ssh"]), default="https")
@click.option("--skip-rag", is_flag=True)
@click.option("--skip-graph", is_flag=True)
@click.option("--limit", type=int, default=None, help="Clone at most N projects (dry-run friendly)")
def gitlab(context_name: str, base_url: str | None, gitlab_group: str | None,
           protocol: str, skip_rag: bool, skip_graph: bool, limit: int | None) -> None:
    global_cfg = load_global()

    # Make context if missing.
    try:
        context_cfg = load_context(context_name)
    except FileNotFoundError:
        context_manager.create(
            context_name,
            display_name=context_name,
            activate=True,
            source_control_base_url=base_url,
            source_control_group=gitlab_group,
        )
        context_cfg = load_context(context_name)

    effective_base = base_url or context_cfg.source_control_base_url
    effective_group = gitlab_group or context_cfg.source_control_group
    if not effective_base:
        raise click.UsageError("--base-url required (or set it on the context)")

    # Resolve auth for gitlab.
    store = get_default_store(global_cfg)
    resolver = AuthResolver(store, global_cfg)
    auth = resolver.resolve(context_cfg, "gitlab")
    click.echo(f"gitlab auth: origin={auth.origin.value}")

    provider = GitLabProvider(
        base_url=effective_base,
        token=auth.bearer if auth.origin.value in {"user_issued", "env_var"} else None,
        oauth_bearer=auth.bearer if auth.origin.value == "oauth_official" else None,
    )

    dest_root = paths.context_repos_dir(context_name)
    dest_root.mkdir(parents=True, exist_ok=True)

    clones: list = []
    with click.progressbar(length=limit or 0, label="cloning") as bar:
        count = 0
        for record in provider.list_projects(group=effective_group):
            if record.payload.get("archived"):
                continue
            result = provider.clone_into(record, dest_root, protocol=protocol)
            clones.append(result)
            count += 1
            if limit and count >= limit:
                break
            if limit:
                bar.update(1)

    click.echo(f"cloned {sum(1 for c in clones if c.cloned)} new, "
               f"{sum(1 for c in clones if not c.cloned)} already-present")

    if not skip_rag:
        click.echo("indexing docs into RAG…")
        stats = index_context(context_name,
                              chunk_size=global_cfg.rag_chunk_size,
                              overlap=global_cfg.rag_chunk_overlap)
        click.echo(f"  rag: scanned={stats.files_scanned} indexed={stats.files_indexed} "
                   f"chunks={stats.chunks_written} skipped={stats.skipped}")

    if not skip_graph:
        click.echo("building code graph…")
        g = build_context_graph(context_name, max_file_bytes=global_cfg.graph_max_file_bytes)
        click.echo(f"  graph: nodes={g.nodes} edges={g.edges} "
                   f"files_scanned={g.files_scanned} skipped={g.files_skipped}")

    click.echo("done.")
