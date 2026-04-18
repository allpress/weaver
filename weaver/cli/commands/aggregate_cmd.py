"""`weaver aggregate …` — fetch authoritative sources to disk. No LLM, no RAG."""
from __future__ import annotations

import json as jsonlib

import click

from weaver.aggregator import (
    CacheLayout,
    fetch_source,
    load_sources,
    load_state,
    save_state,
)
from weaver.aggregator.cache import cache_stats, iter_cached_items
from weaver.aggregator.sources import find_source
from weaver.aggregator.state import get_or_init


@click.group("aggregate", help="Fetch authoritative sources. Indexing is a separate step.")
def group() -> None:
    pass


@group.command("fetch")
@click.option("--context", "context_name", default="ai-corpus", show_default=True)
@click.option("--source", "source_name", default=None,
              help="Restrict to one source by name")
@click.option("--limit", default=None, type=int,
              help="Cap new items per source (dry-tuning)")
@click.option("--force", is_flag=True,
              help="Ignore throttle_seconds on sources")
@click.option("--json", "as_json", is_flag=True)
def fetch(context_name: str, source_name: str | None, limit: int | None,
          force: bool, as_json: bool) -> None:
    # Prefer per-context sources.yaml when present.
    sources = load_sources(context=context_name)
    if source_name:
        s = find_source(sources, source_name)
        if s is None:
            raise click.UsageError(f"unknown source: {source_name}")
        sources = [s]

    layout = CacheLayout(context=context_name)
    layout.root.mkdir(parents=True, exist_ok=True)
    states = load_state(layout)

    results: list[dict[str, object]] = []
    any_halt = False
    for s in sources:
        state = get_or_init(states, s.name)
        if force:
            state.last_fetched_at = None
        result = fetch_source(layout, s, state, limit=limit)
        results.append({
            "source": result.source,
            "feed_status": result.feed_status,
            "not_modified": result.not_modified,
            "throttled": result.throttled,
            "halted": result.halted,
            "halt_reason": result.halt_reason,
            "new": result.new_items,
            "skipped": result.skipped_items,
            "failed": result.failed_items,
            "error": result.error,
        })
        if result.halted:
            any_halt = True
            # Save state before bailing so next run starts clean.
            save_state(layout, states)
            break

    save_state(layout, states)

    if as_json:
        click.echo(jsonlib.dumps(results, indent=2))
        if any_halt:
            raise click.ClickException("aggregator halted — see halt_reason in output")
        return

    total_new = sum(r["new"] for r in results)  # type: ignore[misc]
    for r in results:
        if r["halted"]:
            tag = "HALT"
        elif r["throttled"]:
            tag = "thr "
        elif r["not_modified"]:
            tag = "304 "
        elif r["error"]:
            tag = "err "
        else:
            tag = "ok  "
        note = ""
        if r["halted"]:
            note = f"  HALT: {r['halt_reason']}"
        elif r["error"]:
            note = f"  ERROR: {r['error']}"
        click.echo(
            f"[{tag}] {r['source']:20} +{r['new']:3} new  "
            f"-{r['skipped']:3} seen  !{r['failed']:2} fail{note}"
        )
    click.echo(f"total new: {total_new}")
    if any_halt:
        click.echo("")
        click.echo("aggregator halted early — remaining sources were skipped.")
        click.echo("State was saved; re-run to resume (or wait for Retry-After if rate-limited).")
        raise click.ClickException("halted")


@group.group("sources")
def sources_group() -> None:
    pass


@sources_group.command("list")
@click.option("--context", "context_name", default=None,
              help="If set, show the context's own sources.yaml if present")
@click.option("--json", "as_json", is_flag=True)
def sources_list(context_name: str | None, as_json: bool) -> None:
    sources = load_sources(context=context_name)
    if as_json:
        click.echo(jsonlib.dumps([
            {"name": s.name, "kind": s.kind, "url": s.url,
             "author": s.author, "throttle_seconds": s.throttle_seconds,
             "fetch_article_bodies": s.fetch_article_bodies}
            for s in sources
        ], indent=2))
        return
    for s in sources:
        click.echo(f"{s.name:20} {s.kind:6}  {s.url}")


@group.group("cache")
def cache_group() -> None:
    pass


@cache_group.command("stats")
@click.option("--context", "context_name", default="ai-corpus", show_default=True)
@click.option("--json", "as_json", is_flag=True)
def cache_stats_cmd(context_name: str, as_json: bool) -> None:
    layout = CacheLayout(context=context_name)
    stats = cache_stats(layout)
    if as_json:
        click.echo(jsonlib.dumps(stats, indent=2))
        return
    click.echo(f"context: {context_name}")
    click.echo(f"total:   {stats['total']}")
    for name, n in sorted(stats["per_source"].items()):
        click.echo(f"  {name:20} {n}")


@cache_group.command("list")
@click.option("--context", "context_name", default="ai-corpus", show_default=True)
@click.option("--source", "source_name", default=None)
@click.option("--limit", default=20, show_default=True)
def cache_list(context_name: str, source_name: str | None, limit: int) -> None:
    layout = CacheLayout(context=context_name)
    shown = 0
    for meta in iter_cached_items(layout, source=source_name):
        date_s = meta.published_at.strftime("%Y-%m-%d") if meta.published_at else "?"
        click.echo(f"[{date_s}] {meta.source:20} {meta.title[:80]}")
        shown += 1
        if shown >= limit:
            break
    if shown == 0:
        click.echo("(cache empty — run: weaver aggregate fetch)")


# ---------- indexer (local LLM) ----------

@group.command("index")
@click.option("--context", "context_name", default="ai-corpus", show_default=True)
@click.option("--model", default="qwen2.5:7b", show_default=True,
              help="Ollama model tag; run `ollama pull <model>` first if missing")
@click.option("--ollama-host", default="http://127.0.0.1:11434", show_default=True)
@click.option("--source", "source_filter", default=None,
              help="Only index items from this source")
@click.option("--limit", default=None, type=int,
              help="Cap number of new articles condensed this run")
@click.option("--max-body-chars", default=24_000, show_default=True)
@click.option("--no-rag", is_flag=True, help="Skip ChromaDB upsert")
@click.option("--no-graph", is_flag=True, help="Skip NetworkX graph upsert")
@click.option("--json", "as_json", is_flag=True)
def index_cmd(context_name: str, model: str, ollama_host: str,
              source_filter: str | None, limit: int | None,
              max_body_chars: int, no_rag: bool, no_graph: bool,
              as_json: bool) -> None:
    """Condense cached articles with a local LLM and upsert to RAG + graph."""
    from weaver.indexer import OllamaClient, run_index
    from weaver.indexer.llm_client import OllamaConnectionError

    llm = OllamaClient(model=model, host=ollama_host)

    def _emit(name: str, data: dict) -> None:
        if as_json:
            return
        if name == "condense_done":
            dur = data.get("duration_ms")
            dur_s = f"{dur}ms" if dur is not None else "?ms"
            click.echo(f"  [{dur_s:>7}] {data.get('source', '?'):20} "
                       f"concepts={data['concepts']:2} people={data['people']:2} "
                       f"projects={data['projects']:2}")

    try:
        result = run_index(
            context_name, llm,
            limit=limit, source_filter=source_filter,
            max_body_chars=max_body_chars,
            use_rag=not no_rag, use_graph=not no_graph,
            on_event=_emit,
        )
    except OllamaConnectionError as e:
        raise click.ClickException(str(e)) from e
    finally:
        llm.close()

    if as_json:
        click.echo(jsonlib.dumps({
            "scanned": result.scanned,
            "already_indexed": result.already_indexed,
            "condensed": result.condensed,
            "rag_written": result.rag_written,
            "graph_written": result.graph_written,
            "failed": result.failed,
            "skipped_empty": result.skipped_empty,
            "errors": result.errors[-20:],
        }, indent=2, default=str))
        return

    click.echo("")
    click.echo(f"scanned:         {result.scanned}")
    click.echo(f"already indexed: {result.already_indexed}")
    click.echo(f"condensed:       {result.condensed}")
    click.echo(f"rag written:     {result.rag_written}")
    click.echo(f"graph written:   {result.graph_written}")
    click.echo(f"skipped empty:   {result.skipped_empty}")
    click.echo(f"failed:          {result.failed}")
    if result.failed:
        for err in result.errors[:5]:
            click.echo(f"  err: {err['sha']}  {err['error'][:120]}")


@group.group("llm")
def llm_group() -> None:
    pass


@llm_group.command("status")
@click.option("--ollama-host", default="http://127.0.0.1:11434", show_default=True)
def llm_status(ollama_host: str) -> None:
    """Check Ollama is reachable and list installed models."""
    from weaver.indexer import OllamaClient
    from weaver.indexer.llm_client import OllamaConnectionError

    client = OllamaClient(host=ollama_host)
    try:
        info = client.health()
    except OllamaConnectionError as e:
        raise click.ClickException(str(e)) from e
    finally:
        client.close()

    click.echo(f"host: {info['host']}")
    click.echo("models:")
    for m in info["models"]:
        click.echo(f"  {m}")
    if not info["models"]:
        click.echo("  (none — run: ollama pull qwen2.5:7b)")


@group.group("graph")
def graph_group() -> None:
    pass


@graph_group.command("stats")
@click.option("--context", "context_name", default="ai-corpus", show_default=True)
@click.option("--json", "as_json", is_flag=True)
def graph_stats_cmd(context_name: str, as_json: bool) -> None:
    from weaver.indexer.graph_writer import graph_available, graph_stats
    if not graph_available():
        raise click.ClickException(
            "graph deps missing — install: pip install -e 'weaver[graph]'"
        )
    stats = graph_stats(context_name)
    if as_json:
        click.echo(jsonlib.dumps(stats, indent=2))
        return
    click.echo(f"context:     {context_name}")
    click.echo(f"total nodes: {stats['total_nodes']}")
    click.echo(f"total edges: {stats['total_edges']}")
    click.echo("by kind:")
    for k, n in stats["by_kind"].items():
        click.echo(f"  {k:15} {n}")
