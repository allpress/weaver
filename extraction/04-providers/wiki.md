# Wiki Provider

Supplies documentation/wiki pages. Reference adapter: Confluence.

## Interface

```python
@dataclass
class WikiPage:
    page_id: str
    url: str
    title: str
    space: str
    space_key: str
    content: str                  # cleaned text content
    headings: list[str]
    sections: list[dict]          # [{heading, content}]
    code_blocks: list[dict]       # [{language, code}]
    tables: list[dict]
    images: list[str]
    child_pages: list[str]
    parent_page: Optional[str]
    breadcrumb: list[str]
    labels: list[str]
    last_modified: str
    cached_at: str
    cache_version: int

    def to_rag_chunks(self, chunk_size: int = 1500, overlap: int = 200) -> list[dict]: ...


class Wiki(Provider):
    def get_page(self, page_id_or_url: str) -> WikiPage: ...
    def search(self, query: str, space: Optional[str] = None) -> list[WikiPage]: ...
    def crawl(self, start_url: str, max_pages: int = 500, max_depth: int = 10) -> Iterable[WikiPage]: ...
    def list_pages(self, space: Optional[str] = None, limit: int = 50) -> list[WikiPage]: ...
    def export(self) -> list[dict]: ...       # RAG-ready chunks
```

## Auth Models

- `"api_token"` — Atlassian API token (same credential as JIRA if on same cloud instance). **Preferred.**
- `"browser_sso"` — shared Playwright profile (fallback).

## Content Extraction

Wiki pages are the richest, messiest source type. The cache skill:

- Parses HTML into structured content: preserves headings, lists, tables, code blocks.
- Strips Confluence macros (or renders them — configurable).
- Preserves the breadcrumb so chunks retain page-hierarchy context.
- Extracts inline attachments (images) by URL (doesn't download unless requested).
- Extracts linked-from/linked-to references for graph building.
- Chunks into RAG-friendly segments that respect heading boundaries before falling back to word-count chunking.

## Crawler

`crawl(start_url, max_pages, max_depth)` — BFS from a starting page:
1. Fetch page.
2. Extract content + child-page links.
3. Queue children.
4. Deduplicate by page id.
5. Continue until `max_pages` or `max_depth` reached.

Handles rate limiting, retries on 429, and respects `robots.txt` for external wikis.

## Diagram Extraction

A companion skill (`scripts/playwright_skills/extract_diagrams.py`) renders embedded diagrams (draw.io, Mermaid, Lucidchart exports) to PNG for inclusion in RAG context. Optional; requires Playwright.

## Cache Schema

```
contexts/<name>/cache/wiki/
  index.json               # { last_sync, space, count, page_ids: [...] }
  <page_id>.json           # full WikiPage serialization
```

Like issues, wiki pages contain authenticated content. Caching on disk is opt-in per context.

## Cross-Reference with Source Control

The wiki provider extracts code-block content (often YAML/JSON/commands) which gets embedded for RAG — but also scanned for references to repo names, service names, and API paths, which are fed back into the graph builder to create `references` edges from `WikiPage → Repo/Service/API`.

This is what lets the graph answer "which code does this runbook reference?" and vice-versa.

## CLI Mapping

```
<tool> wiki get | search
<tool> wiki-cache crawl <url> [--max-pages 500 --max-depth 10]
<tool> wiki-cache status | list | search | get | export
```

## Pluggability Checklist

For Notion / Obsidian / Sharepoint / Markdown-folder:

1. `scripts/api_skills/notion_wiki.py` (or a filesystem walker for Markdown folders).
2. Map the provider's page shape to `WikiPage`.
3. For Markdown folders: treat each `.md` file as a page, synthesize `page_id` from path, derive headings/sections by parsing markdown.
4. For Notion: flatten the block tree to sections; use Notion's API pagination.
5. Chunking logic (in the cache skill) is provider-agnostic and reusable.

## Open-Source Reference Adapters

Ship three:
- `scripts/api_skills/confluence_wiki.py`
- `scripts/api_skills/markdown_folder_wiki.py` (no auth — points at a local folder)
- `scripts/api_skills/notion_wiki.py`

Markdown-folder is the lowest-friction starter adapter: drop your `.md` docs in a folder, point the tool at it, and you get a wiki provider for free.
