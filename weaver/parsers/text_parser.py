"""Fallback plain-text parser. Encoding-detected via charset-normalizer."""
from __future__ import annotations

from collections.abc import Iterable

from weaver.parsers.base import ParsedNode, ParseInput, Parser
from weaver.parsers.dispatch import register_parser


class TextParser(Parser):
    name = "text"
    handles_mime = frozenset({"text/plain"})
    handles_ext = frozenset({".txt", ".log", ".ini", ".cfg", ".conf"})

    def parse(self, inp: ParseInput) -> Iterable[ParsedNode]:
        text = _decode(inp.data)
        yield ParsedNode(content=text, kind="text", metadata={"uri": inp.uri or ""})


def _decode(data: bytes | str) -> str:
    if isinstance(data, str):
        return data
    try:
        from charset_normalizer import from_bytes
        result = from_bytes(data).best()
        if result is not None:
            return str(result)
    except ImportError:
        pass
    return data.decode("utf-8", errors="replace")


register_parser(TextParser())
