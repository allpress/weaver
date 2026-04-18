"""Skill ABC + manifest. A skill is a pluggable capability (scrape, read, fetch)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class SkillManifest:
    name: str
    kind: str                              # "api" | "playwright" | "parser" | "domain"
    version: str
    actions: list[str]
    description: str = ""
    requires_secrets: list[str] = field(default_factory=list)
    risk: str = "safe"                     # safe | standard | elevated | dangerous


@dataclass(slots=True)
class SkillResult:
    ok: bool
    data: Any = None
    error: str | None = None


class Skill(ABC):
    manifest: SkillManifest

    @abstractmethod
    def execute(self, action: str, **kwargs: Any) -> SkillResult: ...

    def supports(self, action: str) -> bool:
        return action in self.manifest.actions
