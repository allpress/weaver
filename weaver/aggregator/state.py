"""Per-source fetch state. HTTP caching headers + seen-set."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from weaver.aggregator.cache import CacheLayout


@dataclass(slots=True)
class SourceState:
    name: str
    last_fetched_at: datetime | None = None
    etag: str | None = None
    last_modified: str | None = None
    seen_shas: set[str] = field(default_factory=set)
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "last_fetched_at": self.last_fetched_at.isoformat()
                if self.last_fetched_at else None,
            "etag": self.etag,
            "last_modified": self.last_modified,
            "seen_shas": sorted(self.seen_shas),
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SourceState":
        return cls(
            name=d["name"],
            last_fetched_at=(datetime.fromisoformat(d["last_fetched_at"])
                             if d.get("last_fetched_at") else None),
            etag=d.get("etag"),
            last_modified=d.get("last_modified"),
            seen_shas=set(d.get("seen_shas") or []),
            last_error=d.get("last_error"),
        )


def load_state(layout: CacheLayout) -> dict[str, SourceState]:
    path = layout.state_file
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        name: SourceState.from_dict(data)
        for name, data in raw.items()
    }


def save_state(layout: CacheLayout, state: dict[str, SourceState]) -> None:
    layout.root.mkdir(parents=True, exist_ok=True)
    tmp = layout.state_file.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps({name: s.to_dict() for name, s in state.items()}, indent=2),
        encoding="utf-8",
    )
    tmp.replace(layout.state_file)


def get_or_init(states: dict[str, SourceState], name: str) -> SourceState:
    if name not in states:
        states[name] = SourceState(name=name)
    return states[name]


def throttled(state: SourceState, throttle_seconds: int,
              *, now: datetime | None = None) -> bool:
    """True if we've fetched this source more recently than the throttle window."""
    if state.last_fetched_at is None:
        return False
    n = now or datetime.now(timezone.utc)
    elapsed = (n - state.last_fetched_at).total_seconds()
    return elapsed < throttle_seconds
