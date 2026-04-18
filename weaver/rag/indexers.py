"""Indexers: walk repositories and feed parsed documents into the RAG engine."""
from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from weaver import paths
from weaver.parsers import ParseInput, parse
from weaver.rag.engine import RAGEngine, chunk_text, stable_id

log = logging.getLogger(__name__)

# Documents to index with RAG (docs + text). Code goes to the graph.
_DOC_SUFFIXES = {
    ".md", ".markdown", ".mkd",
    ".rst",
    ".txt",
    ".html", ".htm",
    ".json", ".yaml", ".yml", ".toml",
    ".adoc",
}


@dataclass(slots=True)
class IndexStats:
    files_scanned: int
    files_indexed: int
    chunks_written: int
    skipped: int


def index_context(context: str, *, chunk_size: int = 800, overlap: int = 120) -> IndexStats:
    """Walk the repos in a context, parse docs, push into chroma.

    Collection per repo: "docs::<repo_slug>"
    """
    engine = RAGEngine(context)
    repos_root = paths.context_repos_dir(context)
    if not repos_root.exists():
        return IndexStats(0, 0, 0, 0)

    files_scanned = files_indexed = chunks_written = skipped = 0
    for repo_dir in repos_root.iterdir():
        if not repo_dir.is_dir() or repo_dir.name.startswith("."):
            continue
        repo_slug = repo_dir.name
        items: list[tuple[str, str, dict[str, Any]]] = []

        for path in _doc_files(repo_dir):
            files_scanned += 1
            try:
                data = path.read_bytes()
            except OSError:
                skipped += 1
                continue
            rel = str(path.relative_to(repo_dir))
            try:
                nodes = list(parse(ParseInput(data=data, uri=str(path))))
            except Exception as e:  # noqa: BLE001
                log.warning("parse failed %s: %s", path, e)
                skipped += 1
                continue
            text = _nodes_to_text(nodes)
            if not text.strip():
                skipped += 1
                continue
            for i, chunk in enumerate(chunk_text(text, chunk_size=chunk_size, overlap=overlap)):
                doc_id = stable_id(context, repo_slug, rel, str(i))
                items.append((doc_id, chunk, {
                    "context": context,
                    "repo": repo_slug,
                    "path": rel,
                    "chunk": i,
                    "source_uri": f"file://{path}",
                }))
            files_indexed += 1

        if items:
            collection = f"docs__{_safe(repo_slug)}"
            chunks_written += engine.upsert(collection, items=items)

    return IndexStats(files_scanned, files_indexed, chunks_written, skipped)


def _doc_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if ".git" in p.parts:
            continue
        if p.suffix.lower() in _DOC_SUFFIXES:
            yield p


def _nodes_to_text(nodes: list) -> str:
    out: list[str] = []
    def walk(ns) -> None:
        for n in ns:
            if getattr(n, "content", ""):
                out.append(n.content)
            if getattr(n, "children", None):
                walk(n.children)
    walk(nodes)
    return "\n\n".join(s for s in out if s.strip())


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name).strip("_")[:63] or "repo"
