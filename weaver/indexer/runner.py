"""Orchestrator — walk the aggregator cache, condense new items, upsert to RAG + graph."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from weaver.aggregator.cache import CacheLayout, iter_cached_items, read_item
from weaver.contexts.manifest import load_manifest
from weaver.indexer.condenser import condense_article
from weaver.indexer.html_strip import html_to_text
from weaver.indexer.llm_client import LLMClient, OllamaConnectionError
from weaver.indexer.models import ArticleFacts
from weaver.indexer.state import IndexerState, load_state, save_state

log = logging.getLogger(__name__)


@dataclass(slots=True)
class IndexerResult:
    scanned: int = 0
    already_indexed: int = 0
    condensed: int = 0
    rag_written: int = 0
    graph_written: int = 0
    failed: int = 0
    skipped_empty: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)


ProgressCb = Callable[[str, dict[str, Any]], None]


def run_index(
    context: str,
    llm: LLMClient,
    *,
    limit: int | None = None,
    source_filter: str | None = None,
    max_body_chars: int = 24_000,
    use_rag: bool = True,
    use_graph: bool = True,
    on_event: ProgressCb | None = None,
) -> IndexerResult:
    """Walk the aggregator cache; condense new items with `llm`; upsert writers."""
    layout = CacheLayout(context=context)
    state = load_state(layout)
    result = IndexerResult()

    # Per-context focus pulled from the manifest (if any) — tailors the LLM
    # prompt for this specific knowledge domain.
    manifest = load_manifest(context)
    focus = manifest.focus if manifest else None

    # Lazy-probe writer availability so we can skip cleanly if deps missing.
    rag_ok = graph_ok = False
    if use_rag:
        from weaver.indexer import rag_writer
        rag_ok = rag_writer.rag_available()
        if not rag_ok:
            log.info("RAG deps missing — indexer will skip RAG upserts. "
                     "Install: pip install -e 'weaver[rag]'")
    if use_graph:
        from weaver.indexer import graph_writer
        graph_ok = graph_writer.graph_available()
        if not graph_ok:
            log.info("Graph deps missing — indexer will skip graph upserts. "
                     "Install: pip install -e 'weaver[graph]'")

    processed_in_run = 0
    for meta in iter_cached_items(layout, source=source_filter):
        result.scanned += 1

        if meta.sha in state.indexed_shas:
            result.already_indexed += 1
            continue

        # Load the body from disk.
        try:
            _, body_bytes = read_item(layout, meta.source, meta.sha)
        except Exception as e:  # noqa: BLE001 — cache corruption shouldn't stop the loop
            log.warning("read failed %s/%s: %s", meta.source, meta.sha, e)
            result.failed += 1
            state.mark_failed(meta.sha, f"read: {e}")
            continue

        # HTML → text (or treat already-plain body as text).
        try:
            if meta.content_type and "html" in meta.content_type.lower():
                body_text = html_to_text(body_bytes, max_chars=max_body_chars)
            else:
                body_text = body_bytes.decode("utf-8", errors="replace")
                if len(body_text) > max_body_chars:
                    body_text = body_text[:max_body_chars] + "\n…[truncated]"
        except Exception as e:  # noqa: BLE001
            log.warning("strip failed %s/%s: %s", meta.source, meta.sha, e)
            result.failed += 1
            state.mark_failed(meta.sha, f"strip: {e}")
            continue

        if len(body_text.strip()) < 200:
            # Not enough to condense (probably a nav page or stub). Skip.
            result.skipped_empty += 1
            state.mark_indexed(meta.sha)   # don't re-try next run
            continue

        _emit(on_event, "condense_start", {
            "sha": meta.sha, "source": meta.source, "title": meta.title[:80],
        })

        try:
            extracted, telemetry = condense_article(
                llm,
                source=meta.source, url=meta.url, title=meta.title,
                body_text=body_text, published_at=meta.published_at,
                focus=focus,
                max_body_chars=max_body_chars,
            )
        except OllamaConnectionError as e:
            # LLM unreachable or model missing — halt. Every subsequent item would
            # fail identically; no point walking the rest of the cache.
            log.error("condenser halt on %s/%s: %s", meta.source, meta.sha, e)
            result.failed += 1
            result.errors.append({"sha": meta.sha, "error": str(e)})
            state.mark_failed(meta.sha, str(e))
            save_state(layout, state)
            raise
        except Exception as e:  # noqa: BLE001 — per-item failure shouldn't stop the loop
            log.warning("condenser failed %s/%s: %s", meta.source, meta.sha, e)
            result.failed += 1
            result.errors.append({"sha": meta.sha, "error": str(e)})
            state.mark_failed(meta.sha, str(e))
            continue

        result.condensed += 1
        facts = ArticleFacts(
            sha=meta.sha, source=meta.source, url=meta.url, title=meta.title,
            author=meta.author, published_at=meta.published_at,
            extracted=extracted, indexed_at=datetime.utcnow(),
            model=str(telemetry.get("model") or llm.model),
        )

        if rag_ok:
            try:
                from weaver.indexer.rag_writer import upsert_extracted
                n = upsert_extracted(context, facts)
                result.rag_written += n
            except Exception as e:  # noqa: BLE001
                log.warning("rag upsert failed %s/%s: %s", meta.source, meta.sha, e)
                state.mark_failed(meta.sha, f"rag: {e}")

        if graph_ok:
            try:
                from weaver.indexer.graph_writer import upsert_article_facts
                upsert_article_facts(context, facts)
                result.graph_written += 1
            except Exception as e:  # noqa: BLE001
                log.warning("graph upsert failed %s/%s: %s", meta.source, meta.sha, e)
                state.mark_failed(meta.sha, f"graph: {e}")

        state.mark_indexed(meta.sha)
        processed_in_run += 1

        _emit(on_event, "condense_done", {
            "sha": meta.sha, "source": meta.source,
            "concepts": len(facts.extracted.key_concepts),
            "people": len(facts.extracted.people),
            "projects": len(facts.extracted.projects),
            "duration_ms": telemetry.get("duration_ms"),
        })

        if limit is not None and processed_in_run >= limit:
            break

        # Flush state every 10 items so a crash doesn't lose all progress.
        if processed_in_run % 10 == 0:
            state.last_run_at = datetime.utcnow()
            state.last_model = llm.model
            save_state(layout, state)

    state.last_run_at = datetime.utcnow()
    state.last_model = llm.model
    save_state(layout, state)
    return result


def _emit(cb: ProgressCb | None, name: str, data: dict[str, Any]) -> None:
    if cb is not None:
        try:
            cb(name, data)
        except Exception:  # noqa: BLE001
            log.debug("progress callback raised; continuing")
