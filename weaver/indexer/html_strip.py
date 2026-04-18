"""HTML → plain text. Removes nav/script/style, preserves paragraph breaks."""
from __future__ import annotations

import re


def html_to_text(raw: bytes | str, *, max_chars: int | None = None) -> str:
    """Best-effort extraction. Prefers the article body; falls back to body text."""
    from bs4 import BeautifulSoup

    markup = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    soup = BeautifulSoup(markup, features="lxml")

    # Drop non-content elements before extracting.
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer",
                     "aside", "form", "iframe"]):
        tag.decompose()

    # Prefer explicit article containers; fall back to body.
    container = None
    for selector in ("article", "main", "[role=main]", "[role=article]",
                     ".post-content", ".entry-content", "#content"):
        try:
            container = soup.select_one(selector)
        except Exception:  # noqa: BLE001 — bad CSS shouldn't crash ingest
            container = None
        if container is not None:
            break
    if container is None:
        container = soup.body or soup

    text = container.get_text(separator="\n", strip=True)
    text = _collapse_whitespace(text)

    if max_chars is not None and len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n…[truncated]"
    return text


_MULTI_NL = re.compile(r"\n{3,}")
_MULTI_SP = re.compile(r"[ \t]{2,}")


def _collapse_whitespace(text: str) -> str:
    text = _MULTI_SP.sub(" ", text)
    text = _MULTI_NL.sub("\n\n", text)
    return text.strip()
