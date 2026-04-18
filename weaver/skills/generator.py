"""Skill generator: parse an existing codebase and scaffold a skill from it.

The idea: point weaver at an existing API client / scraper in some repo,
we extract its public surface (functions, endpoints, auth shape) using the
code parser + graph, and emit a skill stub with:
  - SkillManifest (inferred actions from top-level functions)
  - a `_adapter.py` module that wraps the original library
  - a `_skill.py` module registering the adapter under our Skill ABC
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from weaver.parsers import ParseInput, parse

log = logging.getLogger(__name__)


@dataclass(slots=True)
class GeneratedSkill:
    name: str
    directory: Path
    inferred_actions: list[str]
    notes: list[str]


def generate_from_codebase(
    *,
    name: str,
    codebase: Path,
    output_dir: Path,
    kind: str = "api",
) -> GeneratedSkill:
    """Scan `codebase`, infer public surface, write a skill scaffold under `output_dir/<name>/`."""
    codebase = codebase.resolve()
    if not codebase.exists():
        raise FileNotFoundError(codebase)

    inferred: dict[str, list[str]] = {}      # file -> top-level function names
    notes: list[str] = []
    for py in codebase.rglob("*.py"):
        if any(part.startswith(".") for part in py.parts):
            continue
        if "__pycache__" in py.parts or "tests" in py.parts:
            continue
        try:
            data = py.read_bytes()
        except OSError:
            continue
        nodes = list(parse(ParseInput(data=data, uri=str(py))))
        names: list[str] = []
        for n in nodes:
            for child in n.children:
                if child.kind.startswith("def.python.function_definition"):
                    fn = str(child.metadata.get("name", ""))
                    if fn and not fn.startswith("_"):
                        names.append(fn)
        if names:
            inferred[str(py.relative_to(codebase))] = names

    actions = sorted({fn for fns in inferred.values() for fn in fns})
    if not actions:
        notes.append("No public top-level functions found — skill will have no actions.")

    target = (output_dir / name).resolve()
    target.mkdir(parents=True, exist_ok=True)
    (target / "__init__.py").write_text("", encoding="utf-8")
    (target / "_inference.json").write_text(
        json.dumps({"source": str(codebase), "by_file": inferred}, indent=2),
        encoding="utf-8",
    )
    (target / "_skill.py").write_text(_skill_template(name, kind, actions), encoding="utf-8")
    (target / "README.md").write_text(_readme_template(name, kind, codebase, actions), encoding="utf-8")

    return GeneratedSkill(
        name=name,
        directory=target,
        inferred_actions=actions,
        notes=notes,
    )


def _skill_template(name: str, kind: str, actions: list[str]) -> str:
    actions_repr = ", ".join(f'"{a}"' for a in actions) or ""
    return f'''"""{name} skill — auto-generated scaffold. Edit to wire the real adapter."""
from __future__ import annotations

from typing import Any

from weaver.skills.base import Skill, SkillManifest, SkillResult


class {_to_class(name)}Skill(Skill):
    manifest = SkillManifest(
        name="{name}",
        kind="{kind}",
        version="0.1.0",
        actions=[{actions_repr}],
        description="Auto-generated from a source codebase. Fill in the adapter.",
        risk="standard",
    )

    def execute(self, action: str, **kwargs: Any) -> SkillResult:
        # TODO: import and call the real library action.
        if action not in self.manifest.actions:
            return SkillResult(ok=False, error=f"unknown action: {{action}}")
        return SkillResult(ok=False, error=f"action {{action}} not yet wired")


SKILL = {_to_class(name)}Skill()
'''


def _readme_template(name: str, kind: str, codebase: Path, actions: list[str]) -> str:
    bullets = "\n".join(f"- `{a}`" for a in actions) or "_(none inferred)_"
    return f"""# {name} skill

Auto-generated from `{codebase}` ({kind} kind). Review and wire the adapter before use.

## Inferred actions
{bullets}

## Next steps
1. Open `_skill.py` and wire each action to the real implementation.
2. Declare `requires_secrets` on the manifest if the adapter needs tokens.
3. Add tests under `tests/skills/test_{name}.py`.
4. Run: `weaver skill list` to confirm registration.
"""


def _to_class(name: str) -> str:
    return "".join(p.capitalize() for p in name.replace("-", "_").split("_"))
