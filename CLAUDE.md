# Weaver

Bidirectional context-weaving engine for AI agents. Python 3.11+.

## Project Structure
See [extraction/01-architecture/directory-layout.md](extraction/01-architecture/directory-layout.md) for the full layout. Summary:
- `scripts/` — implementation (CLI, ingestion, rag, graph, skills, providers)
- `scripts/rag/` — RAG engine (ChromaDB)
- `scripts/graph/` — Knowledge graph (NetworkX)
- `scripts/skills/`, `scripts/api_skills/`, `scripts/playwright_skills/` — providers + parsers
- `contexts/` — per-context isolated data (repos, caches, indexes)
- `_config/` — global config, known contexts, browser profile
- `docs/` — human-facing docs; `extraction/` — authoritative spec
- `tests/` — pytest suite

## Commands
- `pip install -e .` — install in editable mode
- `pytest` — run tests
- `ruff check .` — lint
- `mypy scripts/` — type check

## Conventions
- Python 3.11+, type hints, `from __future__ import annotations`
- Dataclasses for records; `@dataclass(slots=True, frozen=True)` by default
- `pathlib.Path` over `os.path`; `pydantic` only where validation is needed
- Parsers: use the libraries pinned in [extraction/04-providers/parsers.md](extraction/04-providers/parsers.md) — do not swap without reading the safety notes
- Conventional commits
- Tests alongside implementation
- Apache 2.0 license

## Trio siblings

- **[wayfinder](../wayfinder/)** — web layer. Two APIs: resilient HTTP walker
  (`wayfinder.walk`) and AI-facing browser Session (`wayfinder.browser.Session`).
  Read [wayfinder/wayfinder/browser/AGENTS.md](../wayfinder/wayfinder/browser/AGENTS.md)
  before writing any browser-driving code — handle model, scope rules, ErrCode
  taxonomy are all there.
- **[warden](../warden/)** — guardian daemon. Secrets, policy, the
  `BrowserV2Worker` that hosts a long-lived Session behind `web.*` RPC.

## Driving a browser from weaver

Two modes:

1. **Local, in-process** — scripts, CLI subcommands running outside warden:
   ```python
   from wayfinder.browser import Session, LocalExecutor
   s = Session(LocalExecutor())
   s.open(identity="foo", allowed_domains=["example.com"])
   ```
2. **Warden-hosted** — sandboxed callers:
   ```python
   from wayfinder.browser import WardenWebClient
   from weaver.guardian import warden_client
   with warden_client() as c:
       w = WardenWebClient(c, identity="foo", allowed_domains=["example.com"])
       w.open(); w.goto(url="...")
   ```

The `weaver web` CLI wraps mode 1 for humans; skills that need a browser
should prefer mode 2 so secrets stay inside warden. The old `browser.*` RPC
methods (v1 worker) are deprecated — use `web.*` (v2) for anything new.
