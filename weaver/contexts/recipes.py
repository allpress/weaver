"""Recipe library — pre-built context manifest templates shipped with weaver."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from weaver.contexts.manifest import ContextManifest, ManifestError


@dataclass(slots=True, frozen=True)
class Recipe:
    slug: str
    """Short identifier used on the command line, e.g. `ai-corpus`."""

    path: Path
    """Packaged recipe YAML file."""

    display_name: str
    description: str
    kind: str


def packaged_recipes_dir() -> Path:
    here = Path(__file__).resolve().parent
    return here / "recipes"


def iter_recipes() -> Iterator[Recipe]:
    """Yield every recipe shipped under weaver/contexts/recipes/."""
    from ruamel.yaml import YAML
    yaml = YAML(typ="safe")
    d = packaged_recipes_dir()
    if not d.exists():
        return
    for p in sorted(d.glob("*.yaml")):
        try:
            data = yaml.load(p.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            continue
        yield Recipe(
            slug=p.stem,
            path=p,
            display_name=str(data.get("display_name") or p.stem),
            description=str(data.get("description") or ""),
            kind=str(data.get("kind") or "custom"),
        )


def load_recipe(slug: str, *, as_context_name: str) -> ContextManifest:
    """Load a recipe by slug; return a ContextManifest bound to `as_context_name`."""
    d = packaged_recipes_dir()
    p = d / f"{slug}.yaml"
    if not p.exists():
        available = sorted(r.slug for r in iter_recipes())
        raise ManifestError(
            f"unknown recipe {slug!r}. Available: {available}"
        )
    from ruamel.yaml import YAML
    yaml = YAML(typ="safe")
    try:
        raw = yaml.load(p.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        raise ManifestError(f"cannot parse recipe {p}: {e}") from e
    if not isinstance(raw, dict):
        raise ManifestError(f"recipe root must be a mapping: {p}")

    # The recipe YAML omits `name` (runtime-assigned) and `created_at`.
    raw["name"] = as_context_name
    raw["recipe"] = slug
    raw["created_at"] = datetime.now(timezone.utc).isoformat()
    return ContextManifest.from_dict(raw)
