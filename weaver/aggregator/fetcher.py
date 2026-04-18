"""RSS/Atom fetcher. All HTTP goes through wayfinder so errors halt fast,
hosts with 429/5xx storms circuit-break, and every attempt is a structured event.

No parsing of article content happens here — just dumping bytes to disk. The
indexer (future) walks `iter_cached_items` and decides what to condense.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from weaver.aggregator.cache import (
    CacheLayout,
    ItemMeta,
    compute_sha,
    item_exists,
    write_item,
)
from weaver.aggregator.sources import Source
from weaver.aggregator.state import SourceState, throttled

log = logging.getLogger(__name__)


@dataclass(slots=True)
class FetchResult:
    source: str
    feed_status: int = 0
    feed_bytes: int = 0
    new_items: int = 0
    skipped_items: int = 0
    failed_items: int = 0
    not_modified: bool = False
    throttled: bool = False
    halted: bool = False
    halt_reason: str | None = None
    error: str | None = None
    new_shas: list[str] = field(default_factory=list)


def fetch_source(
    layout: CacheLayout,
    source: Source,
    state: SourceState,
    *,
    http: Any | None = None,
    policy: Any | None = None,
    fetch_article_bodies: bool | None = None,
    now: datetime | None = None,
    limit: int | None = None,
    on_event: Callable[[Any], None] | None = None,
    via_guardian: bool | None = None,
) -> FetchResult:
    """Fetch one source; update `state` in place. Returns a FetchResult.

    Backend selection (see _walk_bridge.resolve_mode):
      - `via_guardian=True` forces Warden-mediated fetches.
      - `via_guardian=False` forces in-process wayfinder (tests, dev).
      - `via_guardian=None` (default): guardian if Warden is running AND no
        custom `http` client was supplied; otherwise direct.
    """
    from wayfinder import FetchPolicy

    from weaver.aggregator._walk_bridge import resolve_mode, walk_bridged

    now = now or datetime.now(timezone.utc)
    result = FetchResult(source=source.name)

    if throttled(state, source.throttle_seconds, now=now):
        result.throttled = True
        return result

    policy = policy or FetchPolicy()
    mode = resolve_mode(http, via_guardian)

    # --- 1) Fetch the feed ---
    feed_headers: dict[str, str] = {
        "Accept": "application/rss+xml, application/atom+xml, */*",
    }
    if state.etag:
        feed_headers["If-None-Match"] = state.etag
    if state.last_modified:
        feed_headers["If-Modified-Since"] = state.last_modified

    feed_report = walk_bridged(
        [{"url": source.url, "headers": feed_headers,
          "tag": f"feed:{source.name}"}],
        policy=policy, mode=mode, context=layout.context,
        http=http, on_event=on_event,
    )

    if feed_report.halted:
        result.halted = True
        result.halt_reason = feed_report.halt_reason
        state.last_error = feed_report.halt_reason
        state.last_fetched_at = now
        return result

    feed_hit = feed_report.successes.get(source.url)
    if feed_hit is None:
        # Feed fetch failed without halting — network error or retry exhausted.
        result.error = "feed fetch failed"
        state.last_error = result.error
        state.last_fetched_at = now
        return result

    result.feed_status = feed_hit.status
    result.feed_bytes = len(feed_hit.body)

    # Handle conditional-get: 304 Not Modified
    if feed_hit.status == 304:
        result.not_modified = True
        state.last_fetched_at = now
        state.last_error = None
        return result

    new_etag = feed_hit.headers.get("etag") or feed_hit.headers.get("ETag")
    new_last_modified = (feed_hit.headers.get("last-modified")
                         or feed_hit.headers.get("Last-Modified"))
    if new_etag:
        state.etag = new_etag
    if new_last_modified:
        state.last_modified = new_last_modified

    # --- 2) Parse entries ---
    entries = _parse_entries(feed_hit.body, source=source)

    fetch_bodies = (
        source.fetch_article_bodies if fetch_article_bodies is None else fetch_article_bodies
    )

    # --- 3) Dedup + build target list for articles we don't have yet ---
    to_fetch: list[tuple[dict[str, Any], str]] = []
    for entry in entries:
        canonical = entry["url"]
        sha = compute_sha(canonical)
        if sha in state.seen_shas or item_exists(layout, source.name, sha):
            result.skipped_items += 1
            state.seen_shas.add(sha)
            continue
        to_fetch.append((entry, sha))
        if limit is not None and len(to_fetch) >= limit:
            break

    if not to_fetch:
        state.last_fetched_at = now
        state.last_error = None
        return result

    # --- 4) Fetch article bodies in one walk (or skip bodies) ---
    if fetch_bodies:
        article_targets = [
            {"url": entry["url"], "tag": f"article:{sha}"}
            for (entry, sha) in to_fetch
        ]
        article_report = walk_bridged(
            article_targets, policy=policy, mode=mode, context=layout.context,
            http=http, on_event=on_event,
        )

        for (entry, sha) in to_fetch:
            canonical = entry["url"]
            hit = article_report.successes.get(canonical)
            if hit is None or hit.status >= 400:
                result.failed_items += 1
                continue
            _store(layout, state, result, now, source, entry, sha,
                   body=hit.body,
                   content_type=(hit.headers.get("content-type")
                                 or hit.headers.get("Content-Type")
                                 or "text/html"),
                   http_status=hit.status,
                   body_filename="body.html")

        if article_report.halted:
            result.halted = True
            result.halt_reason = article_report.halt_reason
            state.last_error = article_report.halt_reason
            state.last_fetched_at = now
            return result
    else:
        for (entry, sha) in to_fetch:
            _store(layout, state, result, now, source, entry, sha,
                   body=(entry.get("summary") or "").encode("utf-8"),
                   content_type="text/plain",
                   http_status=0,
                   body_filename="body.txt")

    state.last_fetched_at = now
    state.last_error = None
    return result


def _store(layout: CacheLayout, state: SourceState, result: FetchResult,
           now: datetime, source: Source, entry: dict[str, Any], sha: str,
           *, body: bytes, content_type: str, http_status: int,
           body_filename: str) -> None:
    canonical = entry["url"]
    meta = ItemMeta(
        sha=sha, source=source.name, url=canonical, canonical_url=canonical,
        title=entry.get("title", "") or "",
        author=entry.get("author") or source.author,
        published_at=entry.get("published_at"),
        fetched_at=now,
        feed_summary=entry.get("summary", "") or "",
        content_type=content_type,
        http_status=http_status,
        body_filename=body_filename,
    )
    write_item(layout, meta=meta, body=body)
    state.seen_shas.add(sha)
    result.new_items += 1
    result.new_shas.append(sha)


# ---- feed parsing ----

def _parse_entries(raw: bytes, *, source: Source) -> list[dict[str, Any]]:
    """Parse RSS/Atom into a uniform list of {url, title, author, published_at, summary}."""
    import feedparser
    parsed = feedparser.parse(raw)
    out: list[dict[str, Any]] = []
    for entry in parsed.entries or []:
        link = _first_link(entry)
        if not link:
            continue
        out.append({
            "url": link,
            "title": getattr(entry, "title", "") or "",
            "author": getattr(entry, "author", None),
            "summary": getattr(entry, "summary", "") or "",
            "published_at": _parse_date(entry),
        })
    return out


def _first_link(entry: Any) -> str | None:
    link = getattr(entry, "link", None)
    if link:
        return str(link)
    links = getattr(entry, "links", None) or []
    for lnk in links:
        href = lnk.get("href") if isinstance(lnk, dict) else None
        if href:
            return str(href)
    return None


def _parse_date(entry: Any) -> datetime | None:
    tpl = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not tpl:
        return None
    try:
        return datetime(*tpl[:6], tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None
