"""Markdown parser: markdown-it-py, CommonMark-compliant, safe default."""
from __future__ import annotations

from collections.abc import Iterable

from weaver.parsers.base import ParsedNode, ParseInput, Parser
from weaver.parsers.dispatch import register_parser


class MarkdownParser(Parser):
    name = "markdown"
    handles_mime = frozenset({"text/markdown", "text/x-markdown"})
    handles_ext = frozenset({".md", ".markdown", ".mkd"})

    def parse(self, inp: ParseInput) -> Iterable[ParsedNode]:
        try:
            from markdown_it import MarkdownIt
        except ImportError as e:
            raise RuntimeError("markdown-it-py required") from e

        md = MarkdownIt("commonmark")
        text = inp.data.decode("utf-8", errors="replace") if isinstance(inp.data, bytes) else inp.data
        tokens = md.parse(text)

        root = ParsedNode(content="", kind="document", metadata={"uri": inp.uri or ""})
        current: ParsedNode = root
        heading_stack: list[tuple[int, ParsedNode]] = []

        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok.type == "heading_open":
                level = int(tok.tag[1])  # h1 -> 1
                inline = tokens[i + 1] if i + 1 < len(tokens) else None
                title = inline.content if inline else ""
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                parent = heading_stack[-1][1] if heading_stack else root
                node = ParsedNode(content=title, kind=f"heading.h{level}", metadata={"level": level})
                parent.children.append(node)
                heading_stack.append((level, node))
                current = node
                i += 3  # open / inline / close
                continue
            if tok.type == "paragraph_open":
                inline = tokens[i + 1] if i + 1 < len(tokens) else None
                if inline:
                    current.children.append(ParsedNode(content=inline.content, kind="paragraph"))
                i += 3
                continue
            if tok.type == "fence":
                current.children.append(ParsedNode(
                    content=tok.content, kind="code",
                    metadata={"lang": tok.info or ""},
                ))
            i += 1

        yield root

    def references(self, inp: ParseInput) -> Iterable[str]:
        try:
            from markdown_it import MarkdownIt
        except ImportError:
            return
        md = MarkdownIt("commonmark")
        text = inp.data.decode("utf-8", errors="replace") if isinstance(inp.data, bytes) else inp.data
        for tok in md.parse(text):
            if tok.type == "inline" and tok.children:
                for child in tok.children:
                    if child.type == "link_open":
                        for k, v in child.attrs.items():
                            if k == "href":
                                yield str(v)


register_parser(MarkdownParser())
