"""Parser registry + dispatch: mime → ext → sniff → text fallback."""
from __future__ import annotations

import os
from collections.abc import Iterable

from weaver.parsers.base import ParsedNode, ParseInput, Parser

_REGISTRY: list[Parser] = []
_BY_NAME: dict[str, Parser] = {}


def register_parser(parser: Parser) -> None:
    if parser.name in _BY_NAME:
        return  # idempotent on re-import
    _REGISTRY.append(parser)
    _BY_NAME[parser.name] = parser


def registered_parsers() -> list[str]:
    return [p.name for p in _REGISTRY]


def get_parser(name: str) -> Parser:
    return _BY_NAME[name]


def parse(inp: ParseInput) -> Iterable[ParsedNode]:
    parser = _resolve(inp)
    yield from parser.parse(inp)


def _resolve(inp: ParseInput) -> Parser:
    if inp.mime:
        for p in _REGISTRY:
            if inp.mime in p.handles_mime:
                return p
    if inp.uri:
        ext = _ext(inp.uri)
        if ext:
            for p in _REGISTRY:
                if ext in p.handles_ext:
                    return p
    sniffed = _sniff(inp.data)
    if sniffed:
        for p in _REGISTRY:
            if sniffed in p.handles_mime:
                return p
    return _BY_NAME["text"]  # fallback always exists


def _ext(uri: str) -> str:
    _, ext = os.path.splitext(uri.split("?", 1)[0].split("#", 1)[0])
    return ext.lower()


def _sniff(data: bytes | str) -> str | None:
    b = data.encode("utf-8", errors="ignore") if isinstance(data, str) else data
    head = b[:512].lstrip()
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.startswith(b"PK\x03\x04"):
        return "application/zip"
    if head.startswith(b"<?xml"):
        return "application/xml"
    if head[:9].lower().startswith(b"<!doctype") or head[:5].lower() == b"<html":
        return "text/html"
    if head.startswith(b"{") or head.startswith(b"["):
        return "application/json"
    return None
