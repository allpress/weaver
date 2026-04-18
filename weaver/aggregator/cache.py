"""Aggregator on-disk cache layout. Raw bytes only; no parsing."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from weaver import paths


@dataclass(slots=True, frozen=True)
class CacheLayout:
    context: str

    @property
    def root(self) -> Path:
        return paths.context_cache_dir(self.context) / "aggregator"

    @property
    def state_file(self) -> Path:
        return self.root / "state.json"

    def items_dir(self, source: str) -> Path:
        return self.root / "items" / source

    def item_dir(self, source: str, sha: str) -> Path:
        return self.items_dir(source) / sha

    def meta_file(self, source: str, sha: str) -> Path:
        return self.item_dir(source, sha) / "meta.json"

    def raw_file(self, source: str, sha: str, *, suffix: str = ".raw") -> Path:
        return self.item_dir(source, sha) / f"body{suffix}"


@dataclass(slots=True)
class ItemMeta:
    sha: str
    source: str
    url: str
    canonical_url: str
    title: str
    author: str | None
    published_at: datetime | None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    feed_summary: str = ""
    content_type: str = ""
    http_status: int = 0
    body_filename: str = "body.raw"

    def to_dict(self) -> dict[str, Any]:
        return {
            "sha": self.sha,
            "source": self.source,
            "url": self.url,
            "canonical_url": self.canonical_url,
            "title": self.title,
            "author": self.author,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "fetched_at": self.fetched_at.isoformat(),
            "feed_summary": self.feed_summary,
            "content_type": self.content_type,
            "http_status": self.http_status,
            "body_filename": self.body_filename,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ItemMeta":
        def _dt(v: Any) -> datetime | None:
            if not v:
                return None
            return datetime.fromisoformat(str(v))
        return cls(
            sha=d["sha"],
            source=d["source"],
            url=d["url"],
            canonical_url=d["canonical_url"],
            title=d.get("title", ""),
            author=d.get("author"),
            published_at=_dt(d.get("published_at")),
            fetched_at=_dt(d.get("fetched_at")) or datetime.now(timezone.utc),
            feed_summary=d.get("feed_summary", ""),
            content_type=d.get("content_type", ""),
            http_status=int(d.get("http_status", 0)),
            body_filename=d.get("body_filename", "body.raw"),
        )


def compute_sha(canonical_url: str) -> str:
    return hashlib.sha1(canonical_url.encode("utf-8")).hexdigest()


def write_item(
    layout: CacheLayout, *,
    meta: ItemMeta, body: bytes,
) -> Path:
    """Atomically write meta.json + body.raw. Returns the item dir."""
    d = layout.item_dir(meta.source, meta.sha)
    d.mkdir(parents=True, exist_ok=True)
    body_path = d / meta.body_filename
    body_path.write_bytes(body)
    layout.meta_file(meta.source, meta.sha).write_text(
        json.dumps(meta.to_dict(), indent=2), encoding="utf-8",
    )
    return d


def item_exists(layout: CacheLayout, source: str, sha: str) -> bool:
    return layout.meta_file(source, sha).exists()


def read_item(layout: CacheLayout, source: str, sha: str) -> tuple[ItemMeta, bytes]:
    meta = ItemMeta.from_dict(json.loads(
        layout.meta_file(source, sha).read_text(encoding="utf-8"),
    ))
    body = (layout.item_dir(source, sha) / meta.body_filename).read_bytes()
    return meta, body


def iter_cached_items(layout: CacheLayout, source: str | None = None) -> Iterator[ItemMeta]:
    """Walk all cached items. Used by the future indexer."""
    items_root = layout.root / "items"
    if not items_root.exists():
        return
    sources = [items_root / source] if source else [
        p for p in items_root.iterdir() if p.is_dir()
    ]
    for sdir in sources:
        if not sdir.exists():
            continue
        for idir in sdir.iterdir():
            meta_path = idir / "meta.json"
            if meta_path.exists():
                try:
                    yield ItemMeta.from_dict(json.loads(meta_path.read_text("utf-8")))
                except Exception:
                    continue


def cache_stats(layout: CacheLayout) -> dict[str, Any]:
    items_root = layout.root / "items"
    per_source: dict[str, int] = {}
    total = 0
    if items_root.exists():
        for sdir in items_root.iterdir():
            if not sdir.is_dir():
                continue
            n = sum(1 for p in sdir.iterdir() if p.is_dir())
            per_source[sdir.name] = n
            total += n
    return {"total": total, "per_source": per_source}
