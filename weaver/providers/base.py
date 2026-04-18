"""Provider ABC shared by all external systems."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ProviderCapability(str, Enum):
    read = "read"
    write = "write"
    playwright_scrape = "playwright_scrape"
    oauth = "oauth"
    api_token = "api_token"
    basic_auth = "basic_auth"


@dataclass(slots=True, frozen=True)
class Record:
    id: str
    type: str
    source_uri: str
    payload: dict[str, Any] = field(default_factory=dict)


class Provider(ABC):
    name: str = "unknown"
    family: str = "unknown"  # issue_tracker | source_control | wiki | log_search | …

    @abstractmethod
    def capabilities(self) -> set[ProviderCapability]: ...

    @abstractmethod
    def fetch(self, **query: Any) -> Iterable[Record]: ...

    def get(self, record_id: str) -> Record:
        raise NotImplementedError(f"{self.name}.get not implemented")
