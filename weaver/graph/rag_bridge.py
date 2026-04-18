"""RAG ↔ graph bridge. Boosts RAG hits by graph centrality and vice versa."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from weaver import paths
from weaver.graph.export import load_json
from weaver.rag.engine import RAGEngine, RAGHit


@dataclass(slots=True)
class BridgedHit:
    rag: RAGHit
    graph_score: float
    combined: float


def bridged_query(context: str, q: str, *, top_k: int = 8,
                  graph_weight: float = 0.3) -> list[BridgedHit]:
    """Query docs via RAG, reweight by importance of the containing file in the graph."""
    engine = RAGEngine(context)
    collections = [c for c in engine.list_collections() if c.startswith("docs__")]
    hits: list[RAGHit] = []
    for col in collections:
        hits.extend(engine.query(col, q, top_k=top_k))

    graph_path = paths.context_graph_dir(context) / "snapshots" / "latest.json"
    centrality = _file_centrality(graph_path) if graph_path.exists() else {}

    combined: list[BridgedHit] = []
    for h in hits:
        path = str(h.metadata.get("path", ""))
        repo = str(h.metadata.get("repo", ""))
        file_key = f"file::{repo}::{path}"
        g_score = centrality.get(file_key, 0.0)
        score = (1.0 - graph_weight) * (1.0 - h.score) + graph_weight * g_score
        combined.append(BridgedHit(rag=h, graph_score=g_score, combined=score))

    combined.sort(key=lambda x: x.combined, reverse=True)
    return combined[:top_k]


def _file_centrality(snapshot: Path) -> dict[str, float]:
    try:
        import networkx as nx
    except ImportError:
        return {}
    g = load_json(snapshot)
    try:
        pr: dict[str, float] = nx.pagerank(g)
    except Exception:
        return {}
    return {k: v for k, v in pr.items() if isinstance(k, str) and k.startswith("file::")}
