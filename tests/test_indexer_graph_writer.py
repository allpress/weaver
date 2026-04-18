"""Graph writer tests — skip cleanly when networkx isn't installed."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

pytest.importorskip("networkx")

from weaver.indexer.graph_writer import (
    _canon,
    graph_stats,
    load_aggregator_graph,
    upsert_article_facts,
)
from weaver.indexer.models import ArticleFacts, ExtractedArticle, Person, Project


def _facts(sha: str, *, people=(), projects=(), concepts=(),
           technologies=(), refs=()) -> ArticleFacts:
    return ArticleFacts(
        sha=sha, source="src-a", url=f"https://example.com/{sha}",
        title=f"Article {sha}", author="Jane",
        published_at=datetime(2025, 4, 1, tzinfo=timezone.utc),
        indexed_at=datetime(2025, 4, 2, tzinfo=timezone.utc),
        model="test-model",
        extracted=ExtractedArticle(
            summary="summary",
            key_concepts=list(concepts),
            people=list(people),
            projects=list(projects),
            technologies=list(technologies),
            references=list(refs),
        ),
    )


def test_canonicalizes_entity_names() -> None:
    assert _canon("Andrej Karpathy") == "andrej-karpathy"
    assert _canon("  LangChain  ") == "langchain"
    assert _canon("N/A") == "n-a"
    assert _canon("") == "unknown"


def test_first_upsert_creates_article_and_related_nodes(tmp_context: Path) -> None:
    facts = _facts(
        "a1",
        people=[Person(name="Andrej Karpathy", role="mentioned"),
                Person(name="Jane Doe", role="author")],
        projects=[Project(name="LangChain", url="https://langchain.com")],
        concepts=["retrieval-augmented generation"],
        technologies=["PyTorch"],
        refs=["https://arxiv.org/abs/2005.11401"],
    )
    stats = upsert_article_facts("ai-corpus", facts)
    # article + source + 2 people + 1 project + 1 concept + 1 technology + 1 url = 8
    assert stats["total_nodes"] == 8
    # article → source, authored_by, mentions, mentions(proj), covers, uses, cites = 7
    assert stats["total_edges"] == 7


def test_second_upsert_is_additive_and_dedupes_nodes(tmp_context: Path) -> None:
    f1 = _facts("a1", people=[Person(name="Andrej Karpathy")],
                 concepts=["RAG"])
    f2 = _facts("a2", people=[Person(name="Andrej Karpathy")],
                 concepts=["RAG"])
    upsert_article_facts("ai-corpus", f1)
    stats = upsert_article_facts("ai-corpus", f2)
    # Two articles but only one person node and one concept node.
    kinds = graph_stats("ai-corpus")["by_kind"]
    assert kinds["article"] == 2
    assert kinds["person"] == 1
    assert kinds["concept"] == 1
    assert stats["total_edges"] > 0


def test_graph_stats_by_kind(tmp_context: Path) -> None:
    upsert_article_facts("ai-corpus", _facts(
        "a1",
        people=[Person(name="X")],
        projects=[Project(name="Y")],
        concepts=["c1", "c2"],
    ))
    stats = graph_stats("ai-corpus")
    assert stats["by_kind"]["article"] == 1
    assert stats["by_kind"]["source"] == 1
    assert stats["by_kind"]["person"] == 1
    assert stats["by_kind"]["project"] == 1
    assert stats["by_kind"]["concept"] == 2


def test_load_returns_none_when_missing(tmp_context: Path) -> None:
    assert load_aggregator_graph("ai-corpus") is None


def test_updates_person_affiliation_with_longer_value(tmp_context: Path) -> None:
    upsert_article_facts("ai-corpus", _facts(
        "a1", people=[Person(name="Lilian Weng", affiliation="OpenAI")]
    ))
    upsert_article_facts("ai-corpus", _facts(
        "a2", people=[Person(name="Lilian Weng", affiliation="OpenAI (prior)")]
    ))
    g = load_aggregator_graph("ai-corpus")
    assert g is not None
    pid = "person::lilian-weng"
    assert g.nodes[pid]["affiliation"] == "OpenAI (prior)"
