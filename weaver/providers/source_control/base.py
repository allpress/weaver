"""Source-control provider interface. Shared by GitLab, GitHub, Gitea, Bitbucket."""
from __future__ import annotations

from abc import abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from weaver.providers.base import Provider, Record


@dataclass(slots=True, frozen=True)
class CloneResult:
    name: str                     # slug
    path: Path                    # on-disk location
    http_url: str
    default_branch: str
    size_kb: int
    languages: dict[str, int] = field(default_factory=dict)
    cloned: bool = False          # True if we actually cloned; False if already present


class SourceControl(Provider):
    family = "source_control"

    @abstractmethod
    def list_projects(self, *, group: str | None = None, **_: Any) -> Iterable[Record]: ...

    @abstractmethod
    def clone_into(self, project: Record, dest_root: Path, *,
                   protocol: str = "https") -> CloneResult: ...
