"""JSON parser: stdlib json, safest on untrusted input."""
from __future__ import annotations

import json
from collections.abc import Iterable

from weaver.parsers.base import ParsedNode, ParseError, ParseInput, Parser
from weaver.parsers.dispatch import register_parser


class JSONParser(Parser):
    name = "json"
    handles_mime = frozenset({"application/json", "text/json"})
    handles_ext = frozenset({".json"})

    def parse(self, inp: ParseInput) -> Iterable[ParsedNode]:
        text = inp.data.decode("utf-8", errors="replace") if isinstance(inp.data, bytes) else inp.data
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            raise ParseError(f"invalid JSON: {e}") from e
        yield ParsedNode(
            content=json.dumps(obj, indent=2, sort_keys=True),
            kind="json",
            metadata={"uri": inp.uri or "", "top_level_type": type(obj).__name__},
        )


register_parser(JSONParser())
