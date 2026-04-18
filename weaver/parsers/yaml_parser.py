"""YAML parser: ruamel.yaml in safe mode."""
from __future__ import annotations

import json
from collections.abc import Iterable

from weaver.parsers.base import ParsedNode, ParseError, ParseInput, Parser
from weaver.parsers.dispatch import register_parser


class YAMLParser(Parser):
    name = "yaml"
    handles_mime = frozenset({"application/yaml", "text/yaml", "text/x-yaml"})
    handles_ext = frozenset({".yaml", ".yml"})

    def parse(self, inp: ParseInput) -> Iterable[ParsedNode]:
        try:
            from ruamel.yaml import YAML
        except ImportError as e:
            raise RuntimeError("ruamel.yaml required") from e

        text = inp.data.decode("utf-8", errors="replace") if isinstance(inp.data, bytes) else inp.data
        yaml = YAML(typ="safe")
        try:
            obj = yaml.load(text)
        except Exception as e:
            raise ParseError(f"invalid YAML: {e}") from e
        yield ParsedNode(
            content=json.dumps(obj, indent=2, sort_keys=True, default=str),
            kind="yaml",
            metadata={"uri": inp.uri or "", "top_level_type": type(obj).__name__},
        )


register_parser(YAMLParser())
