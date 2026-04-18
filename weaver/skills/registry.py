"""Skill registry + dispatch."""
from __future__ import annotations

import importlib
import importlib.util
import logging
from pathlib import Path
from typing import Any

from weaver.paths import repo_root
from weaver.skills.base import Skill, SkillResult

log = logging.getLogger(__name__)


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        name = skill.manifest.name
        if name in self._skills:
            log.debug("skill %s already registered; replacing", name)
        self._skills[name] = skill

    def get(self, name: str) -> Skill:
        if name not in self._skills:
            raise KeyError(f"unknown skill: {name!r}")
        return self._skills[name]

    def list(self) -> list[str]:
        return sorted(self._skills.keys())

    def execute(self, skill_name: str, action: str, **kwargs: Any) -> SkillResult:
        skill = self.get(skill_name)
        if not skill.supports(action):
            return SkillResult(ok=False, error=f"skill {skill_name!r} has no action {action!r}")
        try:
            return skill.execute(action, **kwargs)
        except Exception as e:  # noqa: BLE001
            log.exception("skill %s action %s failed", skill_name, action)
            return SkillResult(ok=False, error=str(e))

    def load_from(self, directory: Path) -> int:
        """Load every *_skill.py under `directory` that defines a `SKILL` attribute."""
        n = 0
        if not directory.exists():
            return 0
        for py in directory.glob("**/*_skill.py"):
            module_name = f"_weaver_dynamic_{py.stem}"
            spec = importlib.util.spec_from_file_location(module_name, py)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
            except Exception as e:  # noqa: BLE001
                log.warning("failed to load %s: %s", py, e)
                continue
            skill = getattr(module, "SKILL", None)
            if isinstance(skill, Skill):
                self.register(skill)
                n += 1
        return n


_DEFAULT: SkillRegistry | None = None


def get_registry() -> SkillRegistry:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = SkillRegistry()
        # Auto-load built-in and user skills.
        _DEFAULT.load_from(repo_root() / "weaver" / "skills" / "builtins")
        _DEFAULT.load_from(repo_root() / "skills_user")
    return _DEFAULT
