"""Fetcher routed through Warden. We stub `weaver.guardian.spawn_wayfinder`
so no daemon is needed, but exercise the full bridge including base64 body
round-tripping and the successes/failures shape the guardian worker returns.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from pathlib import Path

from weaver.aggregator.cache import CacheLayout, item_exists
from weaver.aggregator.fetcher import fetch_source
from weaver.aggregator.sources import Source
from weaver.aggregator.state import SourceState


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


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _make_fake_spawn(responses: dict[str, dict]):
    """responses: {url: {status, body_b64, headers}}"""
    calls: list[dict] = []

    def spawn_wayfinder(type_name, *, context, inputs, on_event=None,
                        poll_interval_s=0, timeout_s=0):
        calls.append({
            "type": type_name, "context": context,
            "targets": [t["url"] for t in inputs.get("targets", [])],
        })
        # Build the response shape the guardian bridge expects.
        successes = {}
        for t in inputs.get("targets", []):
            r = responses.get(t["url"])
            if r is None:
                continue
            successes[t["url"]] = r
        return {
            "spawn_id": "spn_test",
            "status": "completed",
            "output": {
                "successes": successes,
                "failures": [],
                "halted": False,
                "halt_reason": None,
                "broken_hosts": [],
                "events_count": 0,
            },
            "error": None,
        }

    return spawn_wayfinder, calls


def test_fetcher_via_guardian_stores_new_items(tmp_context: Path, monkeypatch) -> None:
    import weaver.guardian as gm

    spawn, calls = _make_fake_spawn({
        "https://example.com/feed": {
            "status": 200,
            "body_b64": _b64(_SAMPLE_FEED),
            "headers": {"etag": 'W/"v1"'},
        },
        "https://example.com/one": {
            "status": 200,
            "body_b64": _b64(b"<html>one</html>"),
            "headers": {"content-type": "text/html"},
        },
        "https://example.com/two": {
            "status": 200,
            "body_b64": _b64(b"<html>two</html>"),
            "headers": {"content-type": "text/html"},
        },
    })
    monkeypatch.setattr(gm, "spawn_wayfinder", spawn)

    layout = CacheLayout(context="ai-corpus")
    layout.root.mkdir(parents=True, exist_ok=True)
    source = Source(name="test", kind="rss", url="https://example.com/feed",
                    throttle_seconds=0)
    state = SourceState(name="test")

    result = fetch_source(layout, source, state, via_guardian=True)

    assert result.new_items == 2
    assert result.skipped_items == 0
    assert state.etag == 'W/"v1"'
    # Two guardian spawns: one feed walk + one article batch.
    assert len(calls) == 2
    assert calls[0]["targets"] == ["https://example.com/feed"]
    assert set(calls[1]["targets"]) == {"https://example.com/one", "https://example.com/two"}
    # Items on disk
    for sha in state.seen_shas:
        assert item_exists(layout, "test", sha)


def test_fetcher_via_guardian_honors_304(tmp_context: Path, monkeypatch) -> None:
    import weaver.guardian as gm

    spawn, _calls = _make_fake_spawn({
        "https://example.com/feed": {
            "status": 304, "body_b64": _b64(b""), "headers": {},
        },
    })
    monkeypatch.setattr(gm, "spawn_wayfinder", spawn)

    layout = CacheLayout(context="ai-corpus")
    layout.root.mkdir(parents=True, exist_ok=True)
    source = Source(name="test", kind="rss", url="https://example.com/feed",
                    throttle_seconds=0)
    state = SourceState(name="test", etag='W/"v1"')

    result = fetch_source(layout, source, state, via_guardian=True)
    assert result.not_modified is True
    assert result.new_items == 0


def test_fetcher_via_guardian_surfaces_halt(tmp_context: Path, monkeypatch) -> None:
    """When the guardian spawn reports halted=True, the fetcher halts cleanly."""
    import weaver.guardian as gm

    def spawn(type_name, *, context, inputs, on_event=None,
              poll_interval_s=0, timeout_s=0):
        return {
            "spawn_id": "spn_x",
            "status": "terminated",
            "output": {
                "successes": {},
                "failures": [],
                "halted": True,
                "halt_reason": "huggingface.co returned 429 (Retry-After=60s)",
                "broken_hosts": ["huggingface.co"],
            },
            "error": "huggingface.co returned 429 (Retry-After=60s)",
        }
    monkeypatch.setattr(gm, "spawn_wayfinder", spawn)

    layout = CacheLayout(context="ai-corpus")
    layout.root.mkdir(parents=True, exist_ok=True)
    source = Source(name="hf", kind="rss", url="https://huggingface.co/feed",
                    throttle_seconds=0)
    state = SourceState(name="hf")

    result = fetch_source(layout, source, state, via_guardian=True)
    assert result.halted is True
    assert "huggingface.co" in (result.halt_reason or "")
    assert state.last_error == result.halt_reason
