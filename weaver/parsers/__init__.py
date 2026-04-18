"""Parser family. See extraction/04-providers/parsers.md."""
from weaver.parsers.base import (
    ParsedNode,
    ParseError,
    ParseInput,
    Parser,
    ParseTimeout,
    ParseTooLarge,
)
from weaver.parsers.dispatch import parse, register_parser, registered_parsers

# Register built-in parsers by importing them for side-effects.
from weaver.parsers import (  # noqa: F401, E402
    code_parser,
    html_parser,
    json_parser,
    markdown_parser,
    text_parser,
    yaml_parser,
)

__all__ = [
    "ParsedNode",
    "ParseError",
    "ParseInput",
    "ParseTimeout",
    "ParseTooLarge",
    "Parser",
    "parse",
    "register_parser",
    "registered_parsers",
]
