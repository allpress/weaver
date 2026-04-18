"""Graph exporters: JSON (node-link) + GraphML."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def export_json(graph: Any, out: Path) -> None:
    import networkx as nx
    data = nx.node_link_data(graph, edges="edges")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def export_graphml(graph: Any, out: Path) -> None:
    import networkx as nx
    out.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(graph, str(out))


def load_json(src: Path) -> Any:
    import networkx as nx
    data = json.loads(src.read_text(encoding="utf-8"))
    return nx.node_link_graph(data, edges="edges")
