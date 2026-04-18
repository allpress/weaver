from __future__ import annotations

import json

import pytest

from weaver.parsers import ParseInput, parse, registered_parsers


def test_builtin_parsers_registered() -> None:
    names = set(registered_parsers())
    assert {"text", "html", "markdown", "json", "yaml", "code"} <= names


def test_text_fallback() -> None:
    out = list(parse(ParseInput(data="hello world", uri="file:///x.unknown")))
    assert out and out[0].content == "hello world"


def test_json_parser_roundtrip() -> None:
    out = list(parse(ParseInput(data='{"a":1}', uri="f.json")))
    assert out
    reparsed = json.loads(out[0].content)
    assert reparsed == {"a": 1}


def test_json_parser_rejects_invalid() -> None:
    from weaver.parsers.base import ParseError
    with pytest.raises(ParseError):
        list(parse(ParseInput(data="{not json", uri="f.json")))


def test_markdown_headings() -> None:
    md = "# Title\n\nBody.\n\n## Sub\n\nMore."
    out = list(parse(ParseInput(data=md, uri="x.md")))
    assert out
    root = out[0]
    kinds = [c.kind for c in root.children]
    assert any(k.startswith("heading.h1") for k in kinds)
