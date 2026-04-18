from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from weaver.aggregator.cache import CacheLayout
from weaver.aggregator.state import (
    SourceState,
    get_or_init,
    load_state,
    save_state,
    throttled,
)


def test_save_and_load_roundtrip(tmp_context: Path) -> None:
    layout = CacheLayout(context="ai-corpus")
    layout.root.mkdir(parents=True, exist_ok=True)
    state = SourceState(
        name="x", last_fetched_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        etag='W/"abc"', last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
        seen_shas={"aaa", "bbb"},
    )
    save_state(layout, {"x": state})
    loaded = load_state(layout)
    assert "x" in loaded
    r = loaded["x"]
    assert r.etag == 'W/"abc"'
    assert r.seen_shas == {"aaa", "bbb"}
    assert r.last_fetched_at == state.last_fetched_at


def test_load_empty_when_missing(tmp_context: Path) -> None:
    layout = CacheLayout(context="ai-corpus")
    assert load_state(layout) == {}


def test_throttled_false_when_never_fetched() -> None:
    s = SourceState(name="x")
    assert throttled(s, 3600) is False


def test_throttled_true_within_window() -> None:
    now = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
    s = SourceState(name="x", last_fetched_at=now - timedelta(seconds=30))
    assert throttled(s, throttle_seconds=3600, now=now) is True


def test_throttled_false_after_window() -> None:
    now = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
    s = SourceState(name="x", last_fetched_at=now - timedelta(hours=2))
    assert throttled(s, throttle_seconds=3600, now=now) is False


def test_get_or_init() -> None:
    d: dict[str, SourceState] = {}
    a = get_or_init(d, "a")
    assert a.name == "a"
    # Second call returns the same instance.
    b = get_or_init(d, "a")
    assert b is a
