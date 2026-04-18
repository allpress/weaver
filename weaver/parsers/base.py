"""Parser ABC and data classes."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field


class ParseError(Exception):
    pass


class ParseTimeout(ParseError):
    pass


class ParseTooLarge(ParseError):
    pass


@dataclass(slots=True, frozen=True)
class ParseInput:
    data: bytes | str
    mime: str | None = None
    uri: str | None = None
    hints: dict[str, str] | None = None


@dataclass(slots=True)
class ParsedNode:
    content: str
    kind: str = "section"
    metadata: dict[str, object] = field(default_factory=dict)
    children: list["ParsedNode"] = field(default_factory=list)


class Parser(ABC):
    name: str = "unknown"
    handles_mime: frozenset[str] = frozenset()
    handles_ext: frozenset[str] = frozenset()

    @abstractmethod
    def parse(self, inp: ParseInput) -> Iterable[ParsedNode]: ...

    def references(self, inp: ParseInput) -> Iterable[str]:  # noqa: ARG002
        return ()

    def _check_size(self, inp: ParseInput, max_bytes: int) -> None:
        size = len(inp.data) if isinstance(inp.data, (bytes, bytearray)) else len(inp.data.encode("utf-8"))
        if size > max_bytes:
            raise ParseTooLarge(f"{self.name}: {size} > {max_bytes}")
