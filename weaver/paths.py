"""Filesystem layout helpers. One source of truth for repo-relative paths."""
from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    """The weaver repo root (directory containing pyproject.toml)."""
    here = Path(__file__).resolve().parent.parent
    if (here / "pyproject.toml").exists():
        return here
    raise RuntimeError(f"Could not locate repo root from {here}")


def config_dir() -> Path:
    return repo_root() / "_config"


def contexts_root() -> Path:
    return repo_root() / "contexts"


def context_dir(name: str) -> Path:
    return contexts_root() / name


def context_repos_dir(name: str) -> Path:
    return context_dir(name) / "repositories"


def context_cache_dir(name: str) -> Path:
    return context_dir(name) / "cache"


def context_chromadb_dir(name: str) -> Path:
    return context_dir(name) / "chromadb"


def context_graph_dir(name: str) -> Path:
    return context_dir(name) / "graph"


def context_config_path(name: str) -> Path:
    return context_dir(name) / "context.ini"


def playwright_auth_dir(context: str, provider: str) -> Path:
    return config_dir() / "playwright" / ".auth" / context / provider
