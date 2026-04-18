"""Fetcher tests — network-free. HTTP goes through wayfinder; we inject a fake."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from wayfinder import FetchPolicy
from wayfinder.http_client import HttpResponse

from weaver.aggregator.cache import CacheLayout, item_exists
from weaver.aggregator.fetcher import fetch_source
from weaver.aggregator.sources import Source
from weaver.aggregator.state import SourceState


class _FakeHttp:
    """Queue-per-URL fake HTTP client compatible with wayfinder's HttpClient."""

    def __init__(self, responses: dict[str, list[HttpResponse] | HttpResponse]) -> None:
        self._q: dict[str, list[HttpResponse]] = {}
        for url, r in responses.items():
            self._q[url] = r if isinstance(r, list) else [r]
        self.calls: list[tuple[str, dict[str, str] | None]] = []

    def get(self, url: str, *, headers: dict[str, str] | None = None,
            timeout: float | None = None) -> HttpResponse:
        self.calls.append((url, dict(headers or {}) or None))
        q = self._q.get(url)
        if not q:
            return HttpResponse(status_code=404, content=b"")
        return q.pop(0) if len(q) > 1 else q[0]


_SAMPLE_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <link>https://example.com/</link>
    <description>Test</description>
    <item>
      <title>Post One</title>
      <link>https://example.com/one</link>
      <pubDate>Mon, 01 Jan 2025 12:00:00 +0000</pubDate>
      <description>summary one</description>
    </item>
    <item>
      <title>Post Two</title>
      <link>https://example.com/two</link>
      <pubDate>Tue, 02 Jan 2025 12:00:00 +0000</pubDate>
      <description>summary two</description>
    </item>
  </channel>
</rss>
"""


def _build_http(*, feed_status: int = 200, feed_headers: dict[str, str] | None = None,
                include_articles: bool = True,
                article_status: int = 200,
                article_headers: dict[str, str] | None = None) -> _FakeHttp:
    responses: dict[str, list[HttpResponse] | HttpResponse] = {
        "https://example.com/feed": HttpResponse(
            status_code=feed_status, content=_SAMPLE_FEED,
            headers=feed_headers or {"etag": 'W/"v1"'},
        ),
    }
    if include_articles:
        responses["https://example.com/one"] = HttpResponse(
            status_code=article_status, content=b"<html>one</html>",
            headers=article_headers or {"content-type": "text/html"},
        )
        responses["https://example.com/two"] = HttpResponse(
            status_code=article_status, content=b"<html>two</html>",
            headers=article_headers or {"content-type": "text/html"},
        )
    return _FakeHttp(responses)


def _policy() -> FetchPolicy:
    """Permissive policy so tests focus on fetcher logic, not halt behaviour."""
    return FetchPolicy(
        max_retries=0,
        halt_after_host_consecutive_failures=99,
        halt_after_global_failures=99,
        halt_on_status=frozenset(),
    )


# ---------- core fetcher behaviour ----------

def test_fetch_stores_new_items(tmp_context: Path) -> None:
    layout = CacheLayout(context="ai-corpus")
    layout.root.mkdir(parents=True, exist_ok=True)
    source = Source(name="test", kind="rss", url="https://example.com/feed", author="T")
    state = SourceState(name="test")
    http = _build_http()

    result = fetch_source(layout, source, state, http=http, policy=_policy())

    assert result.new_items == 2
    assert result.skipped_items == 0
    assert result.failed_items == 0
    assert state.etag == 'W/"v1"'
    assert len(state.seen_shas) == 2
    article_gets = [c for c in http.calls if c[0] != "https://example.com/feed"]
    assert len(article_gets) == 2


def test_fetch_is_idempotent(tmp_context: Path) -> None:
    layout = CacheLayout(context="ai-corpus")
    layout.root.mkdir(parents=True, exist_ok=True)
    source = Source(name="test", kind="rss", url="https://example.com/feed",
                    throttle_seconds=0)
    state = SourceState(name="test")

    http1 = _build_http()
    fetch_source(layout, source, state, http=http1, policy=_policy())
    assert len([c for c in http1.calls if c[0] != "https://example.com/feed"]) == 2

    http2 = _build_http()
    r2 = fetch_source(layout, source, state, http=http2, policy=_policy())
    assert r2.new_items == 0
    assert r2.skipped_items == 2
    assert [c for c in http2.calls if c[0] != "https://example.com/feed"] == []


def test_fetch_honors_304_not_modified(tmp_context: Path) -> None:
    layout = CacheLayout(context="ai-corpus")
    layout.root.mkdir(parents=True, exist_ok=True)
    source = Source(name="test", kind="rss", url="https://example.com/feed")
    state = SourceState(name="test", etag='W/"old"')

    http = _FakeHttp({
        "https://example.com/feed": HttpResponse(status_code=304),
    })
    result = fetch_source(layout, source, state, http=http, policy=_policy())

    assert result.not_modified is True
    assert result.new_items == 0
    _, headers = http.calls[0]
    assert headers is not None
    assert headers.get("If-None-Match") == 'W/"old"'


def test_fetch_handles_article_fetch_failure(tmp_context: Path) -> None:
    layout = CacheLayout(context="ai-corpus")
    layout.root.mkdir(parents=True, exist_ok=True)
    source = Source(name="test", kind="rss", url="https://example.com/feed")
    state = SourceState(name="test")

    http = _build_http(include_articles=False)  # article GETs → 404
    result = fetch_source(layout, source, state, http=http, policy=_policy())

    assert result.new_items == 0
    assert result.failed_items == 2


def test_fetch_no_bodies_stores_summary(tmp_context: Path) -> None:
    layout = CacheLayout(context="ai-corpus")
    layout.root.mkdir(parents=True, exist_ok=True)
    source = Source(name="test", kind="rss", url="https://example.com/feed",
                    fetch_article_bodies=False)
    state = SourceState(name="test")
    http = _build_http(include_articles=False)

    result = fetch_source(layout, source, state, http=http, policy=_policy())
    assert result.new_items == 2
    assert result.failed_items == 0
    article_gets = [c for c in http.calls if c[0] != "https://example.com/feed"]
    assert article_gets == []


def test_fetch_respects_throttle(tmp_context: Path) -> None:
    layout = CacheLayout(context="ai-corpus")
    layout.root.mkdir(parents=True, exist_ok=True)
    source = Source(name="test", kind="rss", url="https://example.com/feed",
                    throttle_seconds=3600)
    now = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
    state = SourceState(name="test", last_fetched_at=now)

    http = _build_http()
    result = fetch_source(layout, source, state, http=http, policy=_policy(), now=now)
    assert result.throttled is True
    assert http.calls == []


def test_fetch_reports_feed_http_error(tmp_context: Path) -> None:
    layout = CacheLayout(context="ai-corpus")
    layout.root.mkdir(parents=True, exist_ok=True)
    source = Source(name="test", kind="rss", url="https://example.com/feed")
    state = SourceState(name="test")

    http = _FakeHttp({
        "https://example.com/feed": HttpResponse(status_code=500),
    })
    # A default policy (halt_on_status includes 503; 500 is just a failure)
    # with max_retries=0 and strict global cap = 1.
    pol = FetchPolicy(max_retries=0, halt_after_global_failures=1,
                      halt_after_host_consecutive_failures=99)
    result = fetch_source(layout, source, state, http=http, policy=pol)
    # Error path — feed fetch failed, no items stored.
    assert result.new_items == 0
    assert result.error or result.halted


def test_fetch_limits_new_items(tmp_context: Path) -> None:
    layout = CacheLayout(context="ai-corpus")
    layout.root.mkdir(parents=True, exist_ok=True)
    source = Source(name="test", kind="rss", url="https://example.com/feed")
    state = SourceState(name="test")
    http = _build_http()

    result = fetch_source(layout, source, state, http=http, policy=_policy(), limit=1)
    assert result.new_items == 1
    article_gets = [c for c in http.calls if c[0] != "https://example.com/feed"]
    assert len(article_gets) == 1


def test_stored_meta_has_expected_fields(tmp_context: Path) -> None:
    layout = CacheLayout(context="ai-corpus")
    layout.root.mkdir(parents=True, exist_ok=True)
    source = Source(name="test", kind="rss", url="https://example.com/feed",
                    author="Fallback Author")
    state = SourceState(name="test")
    http = _build_http()

    fetch_source(layout, source, state, http=http, policy=_policy())
    from weaver.aggregator.cache import iter_cached_items
    metas = list(iter_cached_items(layout, source="test"))
    assert len(metas) == 2
    assert any(m.published_at is not None for m in metas)
    for m in metas:
        assert item_exists(layout, "test", m.sha)


# ---------- wayfinder halt integration ----------

def test_feed_429_halts_fetcher(tmp_context: Path) -> None:
    """A 429 from the feed host should halt immediately with the reason surfaced."""
    layout = CacheLayout(context="ai-corpus")
    layout.root.mkdir(parents=True, exist_ok=True)
    source = Source(name="hf", kind="rss", url="https://huggingface.co/feed")
    state = SourceState(name="hf")
    http = _FakeHttp({
        "https://huggingface.co/feed": HttpResponse(
            status_code=429, headers={"Retry-After": "120"},
        ),
    })
    # Default wayfinder policy halts on 429.
    result = fetch_source(layout, source, state, http=http)

    assert result.halted is True
    assert result.halt_reason is not None
    assert "huggingface.co" in result.halt_reason
    assert "Retry-After=120" in result.halt_reason
    # State records the halt reason so the operator can see it later.
    assert state.last_error == result.halt_reason


def test_article_storm_breaks_host_without_halting_fetcher(tmp_context: Path) -> None:
    """Many article failures trip the host breaker but don't globally halt."""
    layout = CacheLayout(context="ai-corpus")
    layout.root.mkdir(parents=True, exist_ok=True)
    source = Source(name="test", kind="rss", url="https://example.com/feed")
    state = SourceState(name="test")
    http = _build_http(article_status=500)

    pol = FetchPolicy(
        max_retries=0,
        halt_after_host_consecutive_failures=2,
        halt_after_global_failures=99,
        halt_on_status=frozenset(),
    )
    result = fetch_source(layout, source, state, http=http, policy=pol)
    # Feed fetched fine; articles failed. No global halt.
    assert result.halted is False
    assert result.new_items == 0
    assert result.failed_items >= 1


def test_on_event_callback_fires_for_each_request(tmp_context: Path) -> None:
    layout = CacheLayout(context="ai-corpus")
    layout.root.mkdir(parents=True, exist_ok=True)
    source = Source(name="test", kind="rss", url="https://example.com/feed")
    state = SourceState(name="test")
    http = _build_http()

    events: list[Any] = []
    fetch_source(layout, source, state, http=http, policy=_policy(),
                 on_event=events.append)
    # One feed event + two article events.
    assert len(events) == 3
