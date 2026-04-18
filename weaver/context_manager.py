"""Context lifecycle: create, list, inspect, delete. No cross-context writes."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from weaver import paths
from weaver.config import ContextConfig, list_contexts, load_context
from weaver.contexts.manifest import (
    ContextManifest,
    FocusConfig,
    load_manifest,
    save_manifest,
)
from weaver.contexts.recipes import load_recipe


@dataclass(slots=True)
class ContextSummary:
    name: str
    display_name: str
    active: bool
    repos: int
    has_chromadb: bool
    has_graph: bool
    has_manifest: bool = False
    kind: str = "legacy"
    recipe: str | None = None
    description: str = ""


_DEFAULT_CONTEXT_INI = """[context]
display_name = {display}
active = {active}

[sources]
source_control =
issue_tracker =
wiki =
log_search =

[source_control]
base_url = {base_url}
group_or_owner = {group}
clone_protocol = https
"""


def create(name: str, *, display_name: str | None = None, activate: bool = False,
           source_control_base_url: str | None = None,
           source_control_group: str | None = None,
           recipe: str | None = None,
           description: str | None = None,
           kind: str = "custom") -> Path:
    """Create a new context skeleton. Idempotent only if the path is empty.

    If `recipe` is set, the corresponding packaged manifest is instantiated
    alongside the runtime INI. Otherwise a minimal manifest is written so
    every context has one on disk from day one.
    """
    _validate_name(name)
    cdir = paths.context_dir(name)
    if cdir.exists():
        raise FileExistsError(f"Context '{name}' already exists at {cdir}")

    for sub in ("repositories", "cache", "chromadb", "graph/snapshots", "config"):
        (cdir / sub).mkdir(parents=True, exist_ok=True)

    ini = _DEFAULT_CONTEXT_INI.format(
        display=display_name or name,
        active="true" if activate else "false",
        base_url=source_control_base_url or "",
        group=source_control_group or "",
    )
    paths.context_config_path(name).write_text(ini, encoding="utf-8")

    # Write the manifest. If a recipe slug is supplied, instantiate it.
    if recipe:
        manifest = load_recipe(recipe, as_context_name=name)
        if display_name:
            manifest = _replace(manifest, display_name=display_name)
        if description:
            manifest = _replace(manifest, description=description)
    else:
        manifest = ContextManifest(
            name=name,
            display_name=display_name or name,
            description=description or "",
            kind=kind,
            focus=FocusConfig(),
        )
    save_manifest(manifest)

    return cdir


def _replace(m: ContextManifest, **changes) -> ContextManifest:
    """Small frozen-dataclass replace helper (avoids importing dataclasses twice)."""
    import dataclasses
    return dataclasses.replace(m, **changes)


def delete(name: str, *, force: bool = False) -> None:
    cdir = paths.context_dir(name)
    if not cdir.exists():
        raise FileNotFoundError(f"Context '{name}' does not exist")
    if not force:
        raise PermissionError("Refusing to delete without force=True")
    shutil.rmtree(cdir)


def summary(name: str) -> ContextSummary:
    cfg: ContextConfig = load_context(name)
    repos_dir = paths.context_repos_dir(name)
    n_repos = sum(1 for p in repos_dir.iterdir() if p.is_dir()) if repos_dir.exists() else 0
    manifest = load_manifest(name)
    return ContextSummary(
        name=cfg.name,
        display_name=manifest.display_name if manifest else cfg.display_name,
        active=cfg.active,
        repos=n_repos,
        has_chromadb=paths.context_chromadb_dir(name).exists()
            and any(paths.context_chromadb_dir(name).iterdir()),
        has_graph=paths.context_graph_dir(name).exists()
            and any(paths.context_graph_dir(name).iterdir()),
        has_manifest=manifest is not None,
        kind=manifest.kind if manifest else "legacy",
        recipe=manifest.recipe if manifest else None,
        description=manifest.description if manifest else "",
    )


def all_summaries() -> list[ContextSummary]:
    return [summary(n) for n in list_contexts()]


def _validate_name(name: str) -> None:
    if not name or not all(c.isalnum() or c in "-_." for c in name):
        raise ValueError(
            f"Invalid context name: {name!r}. Use alphanumerics, '-', '_', '.'"
        )
