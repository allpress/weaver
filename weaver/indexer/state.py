"""Indexer state — tracks which shas have been indexed, last run metadata."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from weaver.aggregator.cache import CacheLayout


@dataclass(slots=True)
class IndexerState:
    indexed_shas: set[str] = field(default_factory=set)
    last_run_at: datetime | None = None
    last_model: str | None = None
    errors: list[dict[str, Any]] = field(default_factory=list)   # {sha, error, ts}

    def mark_indexed(self, sha: str) -> None:
        self.indexed_shas.add(sha)

    def mark_failed(self, sha: str, error: str) -> None:
        self.errors.append({
            "sha": sha, "error": error[:500],
            "ts": datetime.utcnow().isoformat(),
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "indexed_shas": sorted(self.indexed_shas),
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_model": self.last_model,
            "errors": self.errors[-200:],         # cap at 200 most recent
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "IndexerState":
        return cls(
            indexed_shas=set(d.get("indexed_shas") or []),
            last_run_at=(datetime.fromisoformat(d["last_run_at"])
                         if d.get("last_run_at") else None),
            last_model=d.get("last_model"),
            errors=list(d.get("errors") or []),
        )


def _state_path(layout: CacheLayout) -> Path:
    return layout.root / "indexer_state.json"


def load_state(layout: CacheLayout) -> IndexerState:
    p = _state_path(layout)
    if not p.exists():
        return IndexerState()
    return IndexerState.from_dict(json.loads(p.read_text("utf-8")))


def save_state(layout: CacheLayout, state: IndexerState) -> None:
    layout.root.mkdir(parents=True, exist_ok=True)
    p = _state_path(layout)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state.to_dict(), indent=2, default=str), encoding="utf-8")
    tmp.replace(p)
