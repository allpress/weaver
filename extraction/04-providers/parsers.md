# Parsers

Parsers are a first-class family, peer to [providers](README.md). A **provider** fetches raw bytes/records from an external system; a **parser** turns those bytes into one or more `ContextNode`s with stable `id`, normalized `content`, and structured `metadata`.

Separating these is what lets us point Weaver at *anything*: a new site adds a provider, a new file format adds a parser, and the two compose.

## Parser Contract

Every parser implements the same minimal interface. Like providers, parsers are dispatched through the skill manager.

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

@dataclass(slots=True, frozen=True)
class ParseInput:
    data: bytes | str                   # raw content
    mime: str | None = None             # RFC 6838 if known
    uri: str | None = None              # source URI (file://, https://, jira://…)
    hints: dict[str, str] | None = None # provider-supplied hints (encoding, lang)

@dataclass(slots=True)
class ParsedNode:
    content: str                        # normalized text
    kind: str                           # "section", "table", "code", "image-caption", …
    metadata: dict[str, object]         # page, heading path, lang, bbox, etc.
    children: list["ParsedNode"]        # structural tree (optional)

class Parser(ABC):
    name: str                           # "html", "pdf", "docx", "markdown", …
    handles_mime: frozenset[str]        # {"text/html", "application/xhtml+xml"}
    handles_ext: frozenset[str]         # {".html", ".htm"}

    @abstractmethod
    def parse(self, inp: ParseInput) -> Iterable[ParsedNode]: ...

    # Optional: extract links/references for graph edges
    def references(self, inp: ParseInput) -> Iterable[str]: return ()
```

The parser registry picks an implementation by (mime → ext → content sniff) in that order. Unknown types fall through to the `text` parser (encoding-detected plain text).

## Safety Rules (Non-Negotiable)

Parsers ingest untrusted input. Every implementation must follow these rules:

1. **No network calls during parse.** A parser operates on `ParseInput.data` only. Fetching happens in the provider layer.
2. **No shell, no subprocess.** No `os.system`, no `subprocess.run`. Use in-process libraries only. (Exception: `tree-sitter` native bindings.)
3. **Bounded memory and time.** Every parser takes a `timeout_s` and `max_bytes` from config. Exceeding either raises `ParseTimeout` / `ParseTooLarge` — never partial results silently.
4. **XXE / XML bombs / zip-slip forbidden.** Use `defusedxml` for XML, validate archive entry paths before extraction, refuse symlinks.
5. **Deterministic output.** Same input → same `ParsedNode` tree (including ids). No clock, no random, no locale-dependent sorting.
6. **No C-extension of unknown provenance.** Only libraries listed below. Do not swap for "faster" alternatives without updating this file and threat-modeling.

## Canonical Library per Format

The principle: **stdlib first, one well-maintained library second, no third option.** Each row lists the pinned choice and *why it was picked* — "error-free, safe, fast, hard to misuse."

| Format | Library | Why this one | Notes |
|--------|---------|--------------|-------|
| **HTML** | `beautifulsoup4` with `lxml` backend | Forgiving parser, battle-tested on real-world malformed HTML, lxml backend for speed. `selectolax` is faster but easier to misuse on malformed input. | Set `features="lxml"` explicitly. |
| **Markdown** | `markdown-it-py` | CommonMark-compliant, actively maintained, plugin system, safe by default (no raw HTML eval). `mistune` is faster but drifts from CommonMark. | Use `MarkdownIt("commonmark")`. |
| **JSON** | stdlib `json` | Safest on untrusted input; no custom type coercion. `orjson` only when speed is proven to matter. | Never `eval` JSON. |
| **JSONL / NDJSON** | stdlib `json` + line iterator | Stream one object per line; bounded per-line memory. | |
| **YAML** | `ruamel.yaml` with `typ="safe"` | Round-trippable, safe loader default, preserves comments. `PyYAML.safe_load` also works; ruamel preferred for round-tripping. | **Never** `yaml.load` without `SafeLoader`. |
| **TOML** | stdlib `tomllib` (read), `tomli_w` (write) | Standard-library, spec-correct. | Python 3.11+. |
| **XML** | `defusedxml.ElementTree` | Hardened against XXE, billion laughs, entity expansion, external DTDs. | **Never** raw `xml.etree` or `lxml.etree` on untrusted input. |
| **PDF (text + structure)** | `pypdf` | Pure-Python, maintained, no native deps, safe defaults. | For complex layout/tables, fall through to `pdfplumber`. |
| **PDF (tables / layout)** | `pdfplumber` | Layout-aware extraction, table detection, deterministic. | Slower; use only when `pypdf` output is insufficient. |
| **DOCX** | `python-docx` | Only mainstream .docx library with a sane API. | Ignores macros — treat `.docm` as `.docx`, never execute. |
| **PPTX** | `python-pptx` | Same maintainer as python-docx, consistent API. | Extract text + speaker notes; skip embedded objects. |
| **XLSX (read)** | `python-calamine` | 10–50× faster than openpyxl for reads, supports .xls/.xlsb too, Rust-backed but safe. | Read-only. |
| **XLSX (write)** | `openpyxl` | Canonical writer; calamine is read-only. | Only if we need to produce xlsx. |
| **CSV** | stdlib `csv` + `charset-normalizer` for encoding | Standard and explicit. For typed tabular, use `polars.read_csv` (avoids pandas type-inference footguns). | Always pass `newline=""` when opening. |
| **OpenAPI / Swagger** | `openapi-spec-validator` (validate) + YAML/JSON parser above | Validator catches malformed specs early; actual walking is just dict traversal. `prance` for $ref resolution when needed. | Don't use `openapi-core` unless serving the spec — heavy. |
| **Source code (AST)** | `tree-sitter` via `tree-sitter-languages` | Multi-language, incremental, error-tolerant. Canonical choice across Weaver's code graph. | Already referenced in [directory-layout.md](../01-architecture/directory-layout.md). |
| **Email (.eml / .mbox)** | stdlib `email` + `mailbox` | Safe, complete, no third-party risk surface. | Use `policy.default` for modern headers. |
| **Jupyter notebooks** | `nbformat` | Official Jupyter library; validates against schema. | Strip outputs on parse unless explicitly retained. |
| **reStructuredText** | `docutils` | Reference implementation. | Parse to doctree, walk nodes; don't render to HTML just to re-parse. |
| **LaTeX** | `pylatexenc` | Converts LaTeX → plain text safely without invoking `latex`. | Never shell out to a TeX engine. |
| **ePub** | `ebooklib` | Straightforward, pure Python. | Each chapter is its own `ParsedNode`. |
| **RTF** | `striprtf` | Tiny, text-only extraction. No dependency sprawl. | |
| **Encoding detection** | `charset-normalizer` | Maintained fork of `chardet`, faster, more accurate, no C deps. | Use *before* decoding any unknown bytes. |
| **URLs** | stdlib `urllib.parse` | No third-party footguns. | For joining, `urljoin`, not string concat. |
| **Archives (zip/tar)** | stdlib `zipfile` / `tarfile` + path validation | Validate every entry against zip-slip / tar-slip before extraction. | Never extract symlinks. |
| **Regex (untrusted patterns)** | `google-re2` | Linear-time, ReDoS-safe. | Use for any regex sourced from user/provider input. |
| **Plain text** | stdlib with `charset-normalizer` | Fallback parser for anything unclassified. | Last-resort in the dispatch chain. |

## File Layout

```
scripts/parsers/
  __init__.py
  base.py                 # Parser ABC, ParseInput/ParsedNode, registry
  dispatch.py             # mime → ext → sniff resolution
  text_parser.py          # fallback
  html_parser.py
  markdown_parser.py
  pdf_parser.py
  docx_parser.py
  pptx_parser.py
  xlsx_parser.py
  csv_parser.py
  xml_parser.py           # defusedxml
  yaml_parser.py
  json_parser.py
  toml_parser.py
  openapi_parser.py
  code_parser.py          # tree-sitter wrapper
  email_parser.py
  notebook_parser.py
  rst_parser.py
  latex_parser.py
  epub_parser.py
  rtf_parser.py
  archive_parser.py       # zip/tar with path validation
```

Each file is ~100–200 LOC: imports the canonical library, implements `Parser`, registers via `@register_parser`. No framework needed.

## Dispatch

```python
from scripts.parsers import dispatch

for node in dispatch.parse(ParseInput(data=blob, uri="file:///x.pdf")):
    graph.add_node(node)
```

Resolution order:
1. Explicit MIME from `ParseInput.mime`.
2. Extension from `ParseInput.uri`.
3. Content sniffing (first 512 bytes) — magic numbers for PDF/ZIP/PNG/JPEG/PKZIP; `<!DOCTYPE html>` / `<?xml` sniff.
4. `text_parser` fallback with `charset-normalizer`.

## Configuration

In `_config/context_defaults.ini`:

```ini
[parsers]
timeout_s = 30
max_bytes = 50_000_000
pdf_fallback_to_pdfplumber = true
xlsx_reader = calamine
regex_engine = re2
```

## Adding a New Parser

1. Pick a format not in the table.
2. Research the canonical Python library (stdlib > single well-maintained > everything else).
3. Add a row to the table above *with your safety analysis* (network? shell? native deps? untrusted-input behavior?).
4. Create `scripts/parsers/<format>_parser.py`.
5. Add a pytest covering: (a) happy path, (b) malformed input, (c) size-limit enforcement, (d) deterministic output.
6. Register in `scripts/parsers/__init__.py`.

**Do not** add a second library for a format already listed. If the canonical choice is wrong, replace it (and update every usage in one PR) rather than fork the dispatch table.

## Why Parsers Are Separate From Providers

A provider knows *where* data lives (JIRA Cloud, a Git repo, a Confluence page). A parser knows *what* bytes mean (HTML, PDF, source code). Keeping them separate means:

- New site → one provider, zero parsers (reuses HTML/PDF/etc.).
- New format → one parser, zero providers (works for every source).
- Wayfinder (AI-driven crawler) is just another provider that happens to yield HTML for the HTML parser.
- The weaver operates on `ParsedNode`s and never touches a provider.
