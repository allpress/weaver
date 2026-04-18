"""NetworkX code graph. Nodes = defs + files; edges = defined_in + imports."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from weaver import paths
from weaver.parsers import ParseInput, parse
from weaver.parsers.code_parser import _EXT_LANG, CodeParser

log = logging.getLogger(__name__)


@dataclass(slots=True)
class GraphStats:
    nodes: int
    edges: int
    files_scanned: int
    files_skipped: int


class GraphBuilder:
    def __init__(self) -> None:
        try:
            import networkx as nx
        except ImportError as e:
            raise RuntimeError("networkx required") from e
        self._nx = nx
        self.graph: Any = nx.DiGraph()

    def add_file(self, repo: str, rel_path: str, language: str, size: int) -> str:
        node_id = f"file::{repo}::{rel_path}"
        self.graph.add_node(
            node_id, kind="file", repo=repo, path=rel_path,
            language=language, size=size,
        )
        return node_id

    def add_definition(self, repo: str, rel_path: str, name: str,
                       kind: str, start_line: int, end_line: int) -> str:
        node_id = f"def::{repo}::{rel_path}::{name}"
        self.graph.add_node(
            node_id, kind="def", repo=repo, path=rel_path, name=name,
            def_kind=kind, start_line=start_line, end_line=end_line,
        )
        self.graph.add_edge(f"file::{repo}::{rel_path}", node_id, kind="defined_in")
        return node_id

    def add_import(self, from_file: str, import_text: str) -> None:
        target = f"import::{import_text.strip()[:120]}"
        if not self.graph.has_node(target):
            self.graph.add_node(target, kind="import", specifier=import_text.strip()[:120])
        self.graph.add_edge(from_file, target, kind="imports")


def build_context_graph(context: str, *, max_file_bytes: int = 2_000_000) -> GraphStats:
    repos_root = paths.context_repos_dir(context)
    if not repos_root.exists():
        return GraphStats(0, 0, 0, 0)

    builder = GraphBuilder()
    code_parser = CodeParser()
    files_scanned = files_skipped = 0

    for repo_dir in repos_root.iterdir():
        if not repo_dir.is_dir() or repo_dir.name.startswith("."):
            continue
        repo = repo_dir.name

        for path in repo_dir.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            ext = path.suffix.lower()
            lang = _EXT_LANG.get(ext)
            if lang is None:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > max_file_bytes:
                files_skipped += 1
                continue

            try:
                raw = path.read_bytes()
            except OSError:
                files_skipped += 1
                continue

            rel = str(path.relative_to(repo_dir))
            file_node = builder.add_file(repo, rel, lang, size)

            inp = ParseInput(data=raw, uri=str(path))
            try:
                nodes = list(code_parser.parse(inp))
            except Exception as e:  # noqa: BLE001
                log.debug("code parse failed %s: %s", rel, e)
                files_skipped += 1
                continue

            for n in nodes:
                for child in n.children:
                    if not child.kind.startswith("def."):
                        continue
                    name = str(child.metadata.get("name", "<anon>"))
                    builder.add_definition(
                        repo, rel, name,
                        kind=child.kind,
                        start_line=int(child.metadata.get("start_line", 0)),
                        end_line=int(child.metadata.get("end_line", 0)),
                    )

            try:
                for spec in code_parser.references(inp):
                    builder.add_import(file_node, spec)
            except Exception:
                pass

            files_scanned += 1

    # Persist a snapshot.
    snap_dir = paths.context_graph_dir(context) / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    from weaver.graph.export import export_json
    export_json(builder.graph, snap_dir / "latest.json")

    return GraphStats(
        nodes=builder.graph.number_of_nodes(),
        edges=builder.graph.number_of_edges(),
        files_scanned=files_scanned,
        files_skipped=files_skipped,
    )
