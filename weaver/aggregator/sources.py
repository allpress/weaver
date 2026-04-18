"""Source registry: loads YAML, returns validated Source dataclasses."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from weaver.paths import config_dir, repo_root


@dataclass(slots=True, frozen=True)
class Source:
    name: str
    kind: str                          # "rss" | "atom"
    url: str
    author: str | None = None
    fetch_article_bodies: bool = True
    throttle_seconds: int = 3600


class SourceConfigError(Exception):
    pass


_KINDS = {"rss", "atom"}


def load_sources(path: Path | None = None, *, context: str | None = None) -> list[Source]:
    """Load sources.

    Precedence when `path` not supplied:
      1. `contexts/<context>/sources.yaml`     (if `context` passed)
      2. `_config/aggregator/sources.yaml`     (user-global override)
      3. Packaged seed shipped with weaver
    """
    if path is None:
        if context is not None:
            from weaver import paths as _paths
            ctx_path = _paths.context_dir(context) / "sources.yaml"
            if ctx_path.exists():
                path = ctx_path
        if path is None:
            user_path = config_dir() / "aggregator" / "sources.yaml"
            if user_path.exists():
                path = user_path
            else:
                path = _packaged_seed()

    from ruamel.yaml import YAML
    yaml = YAML(typ="safe")
    raw = yaml.load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("sources") or []

    seen_names: set[str] = set()
    out: list[Source] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise SourceConfigError(f"entry {i}: not a mapping")
        name = entry.get("name")
        kind = entry.get("kind")
        url = entry.get("url")
        if not name or not kind or not url:
            raise SourceConfigError(f"entry {i}: need name, kind, url")
        if kind not in _KINDS:
            raise SourceConfigError(f"{name}: kind {kind!r} not in {sorted(_KINDS)}")
        if name in seen_names:
            raise SourceConfigError(f"duplicate source name: {name!r}")
        seen_names.add(name)
        out.append(Source(
            name=str(name),
            kind=str(kind),
            url=str(url),
            author=entry.get("author"),
            fetch_article_bodies=bool(entry.get("fetch_article_bodies", True)),
            throttle_seconds=int(entry.get("throttle_seconds", 3600)),
        ))
    return out


def _packaged_seed() -> Path:
    """Packaged default. Lives alongside this module."""
    here = Path(__file__).resolve().parent
    return here / "seed-sources.yaml"


def find_source(sources: list[Source], name: str) -> Source | None:
    for s in sources:
        if s.name == name:
            return s
    return None
