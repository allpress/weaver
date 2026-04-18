from __future__ import annotations

from datetime import datetime
from pathlib import Path

from weaver.aggregator.cache import CacheLayout
from weaver.indexer.state import IndexerState, load_state, save_state


def test_load_empty_when_missing(tmp_context: Path) -> None:
    layout = CacheLayout(context="ai-corpus")
    s = load_state(layout)
    assert s.indexed_shas == set()
    assert s.last_run_at is None


def test_mark_indexed_and_save_load_roundtrip(tmp_context: Path) -> None:
    layout = CacheLayout(context="ai-corpus")
    s = IndexerState()
    s.mark_indexed("abc")
    s.mark_indexed("def")
    s.last_run_at = datetime(2025, 4, 1)
    s.last_model = "qwen2.5:7b"
    save_state(layout, s)

    loaded = load_state(layout)
    assert loaded.indexed_shas == {"abc", "def"}
    assert loaded.last_run_at == datetime(2025, 4, 1)
    assert loaded.last_model == "qwen2.5:7b"


def test_errors_truncate_to_200(tmp_context: Path) -> None:
    layout = CacheLayout(context="ai-corpus")
    s = IndexerState()
    for i in range(300):
        s.mark_failed(f"sha{i}", f"err {i}")
    save_state(layout, s)
    loaded = load_state(layout)
    assert len(loaded.errors) == 200
    # Most recent errors are kept — sha299 must be present, sha0 must be gone.
    shas = {e["sha"] for e in loaded.errors}
    assert "sha299" in shas
    assert "sha0" not in shas
