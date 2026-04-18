"""HTML parser: beautifulsoup4 with lxml backend. Yields per-heading sections."""
from __future__ import annotations

from collections.abc import Iterable

from weaver.parsers.base import ParsedNode, ParseInput, Parser
from weaver.parsers.dispatch import register_parser


class HTMLParser(Parser):
    name = "html"
    handles_mime = frozenset({"text/html", "application/xhtml+xml"})
    handles_ext = frozenset({".html", ".htm", ".xhtml"})

    def parse(self, inp: ParseInput) -> Iterable[ParsedNode]:
        try:
            from bs4 import BeautifulSoup
        except ImportError as e:
            raise RuntimeError("beautifulsoup4 + lxml required for HTML parsing") from e

        markup = inp.data.decode("utf-8", errors="replace") if isinstance(inp.data, bytes) else inp.data
        soup = BeautifulSoup(markup, features="lxml")

        # Remove scripts/styles before extraction.
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        root = ParsedNode(content=title, kind="document", metadata={"uri": inp.uri or ""})

        current: ParsedNode | None = None
        for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "pre", "code", "table"]):
            if el.name in {"h1", "h2", "h3", "h4"}:
                current = ParsedNode(
                    content=el.get_text(" ", strip=True),
                    kind=f"section.{el.name}",
                    metadata={},
                )
                root.children.append(current)
            else:
                block = ParsedNode(
                    content=el.get_text(" ", strip=True),
                    kind=el.name,
                    metadata={},
                )
                (current or root).children.append(block)

        yield root

    def references(self, inp: ParseInput) -> Iterable[str]:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return
        markup = inp.data.decode("utf-8", errors="replace") if isinstance(inp.data, bytes) else inp.data
        soup = BeautifulSoup(markup, features="lxml")
        for a in soup.find_all("a", href=True):
            yield str(a["href"])


register_parser(HTMLParser())
