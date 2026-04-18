"""Context manifest — the declarative description of a knowledge domain.

One `manifest.yaml` per context at `contexts/<name>/manifest.yaml`. Sits
alongside the runtime `context.ini` (which holds flags the tool flips —
active, last_synced, etc.). Edit the manifest by hand; runtime state is
managed by the tool.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from weaver import paths

# Bump when we introduce breaking changes to the on-disk shape.
_MANIFEST_VERSION = 1


class ManifestError(Exception):
    pass


@dataclass(slots=True, frozen=True)
class FocusConfig:
    """What the condenser/indexer should prioritize when reading articles."""

    primary_topics: list[str] = field(default_factory=list)
    """The subjects this context cares about. Injected into the LLM prompt."""

    entity_types: list[str] = field(default_factory=list)
    """Entity kinds to extract. Default set:
       person, project, concept, technology, paper, post.
       Business/science contexts can add: company, product, market, gene,
       molecule, trial, institution."""

    exclude_topics: list[str] = field(default_factory=list)
    """Explicit negative guidance — topics to downweight or skip."""

    extra_instruction: str = ""
    """Free-form guidance appended to the system prompt verbatim.
       Use sparingly — prefer primary_topics/entity_types."""


@dataclass(slots=True, frozen=True)
class DecayConfig:
    """Per-node-kind time decay. Applied at query time, not ingest."""

    news_half_life_days: int = 60
    post_half_life_days: int = 90
    concept_half_life_days: int = 730
    project_half_life_days: int = 180
    person_no_decay: bool = True
    revival_min_backlinks: int = 3
    revival_window_days: int = 30


@dataclass(slots=True, frozen=True)
class ContextManifest:
    name: str
    display_name: str
    description: str
    kind: str
    """kind is a free tag — "knowledge-domain", "company-intel",
    "repo-work", "science-watch", "custom". Drives which entity_types and
    decay defaults make sense."""
    focus: FocusConfig = field(default_factory=FocusConfig)
    decay: DecayConfig = field(default_factory=DecayConfig)
    recipe: str | None = None
    """If derived from a recipe, the recipe's slug. Informational only."""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    manifest_version: int = _MANIFEST_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "kind": self.kind,
            "recipe": self.recipe,
            "created_at": self.created_at.isoformat(),
            "manifest_version": self.manifest_version,
            "focus": {
                "primary_topics": list(self.focus.primary_topics),
                "entity_types": list(self.focus.entity_types),
                "exclude_topics": list(self.focus.exclude_topics),
                "extra_instruction": self.focus.extra_instruction,
            },
            "decay": {
                "news_half_life_days": self.decay.news_half_life_days,
                "post_half_life_days": self.decay.post_half_life_days,
                "concept_half_life_days": self.decay.concept_half_life_days,
                "project_half_life_days": self.decay.project_half_life_days,
                "person_no_decay": self.decay.person_no_decay,
                "revival_min_backlinks": self.decay.revival_min_backlinks,
                "revival_window_days": self.decay.revival_window_days,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextManifest":
        missing = {"name", "display_name", "kind"} - set(data.keys())
        if missing:
            raise ManifestError(f"missing required fields: {sorted(missing)}")
        focus_raw = data.get("focus") or {}
        decay_raw = data.get("decay") or {}

        created_raw = data.get("created_at")
        if isinstance(created_raw, datetime):
            created = created_raw
        elif isinstance(created_raw, str):
            try:
                created = datetime.fromisoformat(created_raw)
            except ValueError as e:
                raise ManifestError(f"bad created_at: {created_raw!r}") from e
        else:
            created = datetime.now(timezone.utc)

        return cls(
            name=str(data["name"]),
            display_name=str(data["display_name"]),
            description=str(data.get("description", "") or ""),
            kind=str(data["kind"]),
            focus=FocusConfig(
                primary_topics=list(focus_raw.get("primary_topics") or []),
                entity_types=list(focus_raw.get("entity_types") or []),
                exclude_topics=list(focus_raw.get("exclude_topics") or []),
                extra_instruction=str(focus_raw.get("extra_instruction") or ""),
            ),
            decay=DecayConfig(
                news_half_life_days=int(decay_raw.get("news_half_life_days", 60)),
                post_half_life_days=int(decay_raw.get("post_half_life_days", 90)),
                concept_half_life_days=int(decay_raw.get("concept_half_life_days", 730)),
                project_half_life_days=int(decay_raw.get("project_half_life_days", 180)),
                person_no_decay=bool(decay_raw.get("person_no_decay", True)),
                revival_min_backlinks=int(decay_raw.get("revival_min_backlinks", 3)),
                revival_window_days=int(decay_raw.get("revival_window_days", 30)),
            ),
            recipe=data.get("recipe"),
            created_at=created,
            manifest_version=int(data.get("manifest_version", _MANIFEST_VERSION)),
        )


def manifest_path(context_name: str) -> Path:
    return paths.context_dir(context_name) / "manifest.yaml"


def load_manifest(context_name: str) -> ContextManifest | None:
    """Return the manifest for a context, or None if it has none (legacy ctx)."""
    p = manifest_path(context_name)
    if not p.exists():
        return None
    return _read_yaml(p)


def save_manifest(manifest: ContextManifest) -> Path:
    p = manifest_path(manifest.name)
    p.parent.mkdir(parents=True, exist_ok=True)
    _write_yaml(p, manifest.to_dict())
    return p


def _read_yaml(path: Path) -> ContextManifest:
    from ruamel.yaml import YAML
    yaml = YAML(typ="safe")
    try:
        data = yaml.load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001 — yaml can raise many shapes
        raise ManifestError(f"cannot parse {path}: {e}") from e
    if not isinstance(data, dict):
        raise ManifestError(f"manifest root must be a mapping: {path}")
    return ContextManifest.from_dict(data)


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    from ruamel.yaml import YAML
    from ruamel.yaml.representer import RoundTripRepresenter
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.Representer = RoundTripRepresenter
    tmp = path.with_suffix(".yaml.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        yaml.dump(data, f)
    tmp.replace(path)
