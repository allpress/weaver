"""End-to-end indexer test — fakes the LLM so there's no Ollama dependency.

Covers: cache walk, html strip, condense, state idempotency, on_event callback,
graceful skip when cache entry is too short.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from weaver.aggregator.cache import CacheLayout, ItemMeta, write_item
from weaver.indexer.llm_client import LLMClient, LLMCompletion
from weaver.indexer.runner import run_index
from weaver.indexer.state import load_state


class _ScriptedLLM:
    """Returns a deterministic JSON payload every call."""

    model = "test-model"

    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self._payloads = payloads
        self.calls = 0

    def complete_json(self, *, system: str, user: str,
                      temperature: float = 0.0, timeout_s: float = 0) -> LLMCompletion:
        i = min(self.calls, len(self._payloads) - 1)
        self.calls += 1
        return LLMCompletion(
            model=self.model,
            content=json.dumps(self._payloads[i]),
            total_duration_ms=42,
            prompt_tokens=100,
            completion_tokens=50,
        )


def _seed(layout: CacheLayout, source: str, sha: str, body: bytes,
          title: str = "Test", content_type: str = "text/html") -> None:
    layout.root.mkdir(parents=True, exist_ok=True)
    meta = ItemMeta(
        sha=sha, source=source, url=f"https://example.com/{sha}",
        canonical_url=f"https://example.com/{sha}",
        title=title, author="Tester",
        published_at=datetime(2025, 4, 1, tzinfo=timezone.utc),
        content_type=content_type,
        body_filename="body.html" if "html" in content_type else "body.txt",
    )
    write_item(layout, meta=meta, body=body)


_GOOD_EXTRACTION = {
    "summary": "A long enough summary describing the article content in multiple sentences.",
    "key_concepts": ["retrieval-augmented generation", "agent loops"],
    "people": [{"name": "Jane Doe", "role": "author"},
               {"name": "Andrej Karpathy", "role": "mentioned"}],
    "projects": [{"name": "LangChain", "url": "https://langchain.com",
                  "description": "agent framework"}],
    "technologies": ["PyTorch", "ChromaDB"],
    "references": ["https://arxiv.org/abs/2005.11401"],
}


@pytest.fixture
def seeded_cache(tmp_context: Path) -> CacheLayout:
    layout = CacheLayout(context="ai-corpus")
    good_html = ("<html><body><article><h1>Title</h1>" +
                 "<p>" + ("Real article prose. " * 100) + "</p>" +
                 "</article></body></html>").encode("utf-8")
    _seed(layout, "src-a", "aaa111", good_html, title="Post A")
    _seed(layout, "src-a", "bbb222", good_html, title="Post B")
    # Empty / stub body — should be skipped, not condensed.
    _seed(layout, "src-b", "tiny00", b"<html><body><p>x</p></body></html>",
          title="Too short")
    return layout


def test_run_indexes_cached_items(seeded_cache: CacheLayout) -> None:
    llm = _ScriptedLLM([_GOOD_EXTRACTION])
    result = run_index("ai-corpus", llm, use_rag=False, use_graph=False)
    assert result.scanned == 3
    assert result.condensed == 2
    assert result.skipped_empty == 1
    assert result.failed == 0
    # Model was called twice — once per substantive article; the tiny one never reached the LLM.
    assert llm.calls == 2


def test_idempotency_skips_already_indexed(seeded_cache: CacheLayout) -> None:
    llm1 = _ScriptedLLM([_GOOD_EXTRACTION])
    run_index("ai-corpus", llm1, use_rag=False, use_graph=False)

    llm2 = _ScriptedLLM([_GOOD_EXTRACTION])
    r2 = run_index("ai-corpus", llm2, use_rag=False, use_graph=False)
    assert r2.condensed == 0
    assert r2.already_indexed == 3       # all three shas now in seen set
    assert llm2.calls == 0


def test_limit_caps_new_items(seeded_cache: CacheLayout) -> None:
    llm = _ScriptedLLM([_GOOD_EXTRACTION])
    result = run_index("ai-corpus", llm, use_rag=False, use_graph=False, limit=1)
    assert result.condensed == 1
    assert llm.calls == 1


def test_source_filter_restricts_walk(seeded_cache: CacheLayout) -> None:
    llm = _ScriptedLLM([_GOOD_EXTRACTION])
    result = run_index("ai-corpus", llm, source_filter="src-b",
                        use_rag=False, use_graph=False)
    # src-b only has the tiny stub → it's skipped_empty, not condensed.
    assert result.scanned == 1
    assert result.skipped_empty == 1
    assert result.condensed == 0


def test_on_event_fires_for_each_condensed(seeded_cache: CacheLayout) -> None:
    events: list[tuple[str, dict]] = []
    llm = _ScriptedLLM([_GOOD_EXTRACTION])
    run_index("ai-corpus", llm, use_rag=False, use_graph=False,
               on_event=lambda n, d: events.append((n, d)))
    starts = [e for e in events if e[0] == "condense_start"]
    dones = [e for e in events if e[0] == "condense_done"]
    assert len(starts) == 2
    assert len(dones) == 2
    assert dones[0][1]["concepts"] == len(_GOOD_EXTRACTION["key_concepts"])


def test_state_persisted_with_successes(seeded_cache: CacheLayout) -> None:
    llm = _ScriptedLLM([_GOOD_EXTRACTION])
    run_index("ai-corpus", llm, use_rag=False, use_graph=False)
    state = load_state(seeded_cache)
    assert {"aaa111", "bbb222", "tiny00"}.issubset(state.indexed_shas)
    assert state.last_model == "test-model"


def test_per_item_llm_failure_records_but_continues(seeded_cache: CacheLayout) -> None:
    # Return invalid JSON every call → exhausts retries, marks per-item as failed
    # but does not stop the whole run.
    class _AlwaysBad:
        model = "bad"
        calls = 0
        def complete_json(self, *, system: str, user: str,
                          temperature: float = 0.0, timeout_s: float = 0) -> LLMCompletion:
            _AlwaysBad.calls += 1
            return LLMCompletion(model="bad", content="definitely not json")

    result = run_index("ai-corpus", _AlwaysBad(), use_rag=False, use_graph=False)
    assert result.failed == 2
    assert result.condensed == 0
    assert len(result.errors) == 2
