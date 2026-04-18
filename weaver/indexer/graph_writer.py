"""Upsert condensed article into the per-context NetworkX graph.

Schema:
  Nodes   (kind attribute):
    article    — one per ingested article
    source     — one per RSS/HTML source
    person     — thought leaders, authors, mentioned individuals
    project    — software projects / frameworks
    concept    — canonical concept names
    technology — libraries, tools, algorithms, model names

  Edges (kind attribute):
    article  —from→      source
    article  —authored_by→ person      (role == "author")
    article  —mentions→    person      (role != "author")
    article  —mentions→    project
    article  —covers→      concept
    article  —uses→        technology
    article  —cites→       url         (url nodes are stubs for future resolution)
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from weaver.indexer.models import ArticleFacts

log = logging.getLogger(__name__)


class GraphUnavailable(RuntimeError):
    pass


def graph_available() -> bool:
    try:
        import networkx  # noqa: F401
    except ImportError:
        return False
    return True


def upsert_article_facts(context: str, facts: ArticleFacts) -> dict[str, int]:
    """Load the context graph, add/update article + related entities, save."""
    try:
        import networkx as nx
    except ImportError as e:
        raise GraphUnavailable(
            "Graph deps missing. Install: pip install -e 'weaver[graph]'"
        ) from e

    from weaver import paths
    from weaver.graph.export import export_json, load_json

    snap_dir = paths.context_graph_dir(context) / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap = snap_dir / "aggregator.json"

    g = load_json(snap) if snap.exists() else nx.DiGraph()

    added_nodes = 0
    added_edges = 0

    article_id = f"article::{facts.source}::{facts.sha}"
    if not g.has_node(article_id):
        added_nodes += 1
    g.add_node(
        article_id,
        kind="article",
        title=facts.title,
        url=facts.url,
        source=facts.source,
        published_at=facts.published_at.isoformat() if facts.published_at else None,
        indexed_at=facts.indexed_at.isoformat(),
        summary=facts.extracted.summary[:2000],
    )

    source_id = f"source::{facts.source}"
    if not g.has_node(source_id):
        g.add_node(source_id, kind="source", name=facts.source)
        added_nodes += 1
    if not g.has_edge(article_id, source_id):
        g.add_edge(article_id, source_id, kind="from")
        added_edges += 1

    for person in facts.extracted.people:
        pid = f"person::{_canon(person.name)}"
        if not g.has_node(pid):
            g.add_node(pid, kind="person", name=person.name,
                       affiliation=person.affiliation or "")
            added_nodes += 1
        else:
            # Keep the longest known affiliation (best info wins).
            if person.affiliation:
                existing = g.nodes[pid].get("affiliation") or ""
                if len(person.affiliation) > len(existing):
                    g.nodes[pid]["affiliation"] = person.affiliation

        edge_kind = "authored_by" if (person.role or "").lower() == "author" else "mentions"
        if not g.has_edge(article_id, pid):
            g.add_edge(article_id, pid, kind=edge_kind)
            added_edges += 1

    for project in facts.extracted.projects:
        pid = f"project::{_canon(project.name)}"
        if not g.has_node(pid):
            g.add_node(pid, kind="project", name=project.name,
                       url=project.url or "", description=project.description or "")
            added_nodes += 1
        else:
            if project.url:
                g.nodes[pid]["url"] = g.nodes[pid].get("url") or project.url
        if not g.has_edge(article_id, pid):
            g.add_edge(article_id, pid, kind="mentions")
            added_edges += 1

    for concept in facts.extracted.key_concepts:
        cid = f"concept::{_canon(concept)}"
        if not g.has_node(cid):
            g.add_node(cid, kind="concept", name=concept)
            added_nodes += 1
        if not g.has_edge(article_id, cid):
            g.add_edge(article_id, cid, kind="covers")
            added_edges += 1

    for tech in facts.extracted.technologies:
        tid = f"technology::{_canon(tech)}"
        if not g.has_node(tid):
            g.add_node(tid, kind="technology", name=tech)
            added_nodes += 1
        if not g.has_edge(article_id, tid):
            g.add_edge(article_id, tid, kind="uses")
            added_edges += 1

    for ref_url in facts.extracted.references:
        uid = f"url::{ref_url.strip()[:250]}"
        if not g.has_node(uid):
            g.add_node(uid, kind="url", url=ref_url)
            added_nodes += 1
        if not g.has_edge(article_id, uid):
            g.add_edge(article_id, uid, kind="cites")
            added_edges += 1

    export_json(g, snap)
    return {"nodes_added": added_nodes, "edges_added": added_edges,
            "total_nodes": g.number_of_nodes(), "total_edges": g.number_of_edges()}


_NONALPHANUM = re.compile(r"[^a-z0-9]+")


def _canon(name: str) -> str:
    """Canonicalize entity names for node ID generation."""
    s = (name or "").strip().lower()
    return _NONALPHANUM.sub("-", s).strip("-")[:80] or "unknown"


def load_aggregator_graph(context: str) -> Any:
    """Return the aggregator graph (NetworkX DiGraph) or None if none saved yet."""
    try:
        import networkx as nx  # noqa: F401
    except ImportError as e:
        raise GraphUnavailable("graph deps missing") from e
    from weaver import paths
    from weaver.graph.export import load_json

    snap = paths.context_graph_dir(context) / "snapshots" / "aggregator.json"
    if not snap.exists():
        return None
    return load_json(snap)


def graph_stats(context: str) -> dict[str, Any]:
    """Counts per node-kind. Cheap way to confirm the graph is growing."""
    g = load_aggregator_graph(context)
    if g is None:
        return {"total_nodes": 0, "total_edges": 0, "by_kind": {}}
    by_kind: dict[str, int] = {}
    for _, data in g.nodes(data=True):
        k = str(data.get("kind") or "?")
        by_kind[k] = by_kind.get(k, 0) + 1
    return {
        "total_nodes": g.number_of_nodes(),
        "total_edges": g.number_of_edges(),
        "by_kind": dict(sorted(by_kind.items())),
    }
