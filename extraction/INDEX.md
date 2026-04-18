# Extraction Index

Full table of contents for the open-source rebuild blueprint.

## Start Here

1. [README](README.md) — how to use this blueprint
2. [Vision](00-overview/vision.md) — what we're building and why

## Architecture

3. [Directory Layout](01-architecture/directory-layout.md)
4. [Multi-Context Architecture & Data Flow](01-architecture/multi-context.md)

## CLI

5. [Commands](02-cli/commands.md) — complete command surface, dispatch pattern, cross-cutting flags, generalization notes

## Install / Setup / Config

6. [Install, Wizard, Config](03-install-setup/install-wizard-config.md) — `install.py` phases, setup wizard flow, config system, known-context pattern, linking

## Pluggable Providers

7. [Providers Overview](04-providers/README.md) — the core abstraction
8. [Issue Tracker](04-providers/issue-tracker.md)
9. [Source Control](04-providers/source-control.md)
10. [Log Search](04-providers/log-search.md)
11. [Wiki](04-providers/wiki.md)
12. [ITSM / Cloud Logs / CI/CD](04-providers/itsm-and-cloud-logs-and-ci.md)
12a. [Parsers](04-providers/parsers.md) — first-class peer family; canonical Python library per format
12b. [Auth & Secrets](04-providers/auth-and-secrets.md) — protected-var store, precedence chain, `dangerously_use_playwright_token`

## Core Modules

13. [Core Modules](05-modules/core-modules.md) — RAG, graph, cache/context/sync managers, indexer, CDP watcher, auth, dashboard, video intelligence

## Skills

14. [Skills Catalog](06-skills/skills-catalog.md) — base interface, domain/API/Playwright skill families, per-skill blueprints

## Tests

15. [Test Strategy & Catalog](07-tests/test-strategy-and-catalog.md) — pytest config, shared fixtures, tiered integration tests, per-test blueprints, CI recommendations

## Data Models

16. [Schemas](08-data-models/schemas.md) — all cache and index file shapes (repo cache, issue cache, wiki cache, graph JSON, analysis report, sync status, token cache, hash index)

## AI Integration

17. [AI Tools Integration](09-ai-integration/ai-tools-integration.md) — CLAUDE.md pattern, slash-command skills, project linking, voice/personality

## Ideas & Roadmap

18. [Ideas & Roadmap](10-ideas-roadmap/ideas-and-roadmap.md) — original ideas, new ideas added during use, what to build next, philosophical tenets

---

## Rebuild Order

If you're starting from zero, build in this order:

### Phase 1 — Core skeleton (week 1)
1. `<tool>.py` CLI dispatcher with `context`, `clone`, `pull`, `cache`, `query` commands
2. `install.py` bootstrap (venv, minimal deps, cert propagation)
3. `scripts/config.py` + `_config/defaults.ini.template`
4. `scripts/context_manager.py` + `contexts/` layout
5. `scripts/cache_manager.py` + `scripts/indexer.py`
6. `CLAUDE.md` + `docs/claude/commands.md`

### Phase 2 — One provider (week 2)
7. Provider base classes (`scripts/api_skills/base.py`, `scripts/playwright_skills/base.py`)
8. One source-control adapter (GitHub or GitLab)
9. `scripts/skill_manager.py`
10. `scripts/sync_manager.py`
11. Tests for the above

### Phase 3 — RAG (week 3)
12. `scripts/rag/` (engine, chunker, embedding backend detection, indexers)
13. `rag` CLI commands
14. Minimum cross-context RAG
15. Dashboard skeleton (`dashboard/server.py` + `/api/overview`)

### Phase 4 — Graph (week 4)
16. `scripts/graph/` (builder, analyzer, exporter, diff)
17. `graph` CLI commands
18. Dashboard `viz.html` with vis.js
19. Graph↔RAG bridge

### Phase 5 — Additional providers (ongoing)
20. Issue tracker adapter (JIRA or GitHub Issues)
21. Wiki adapter (Markdown folder first, Confluence/Notion later)
22. Log search adapter (Splunk or OpenSearch)
23. Cloud logs adapter (CloudWatch)

### Phase 6 — AI integration
24. `scripts/claude_skills_manager.py`
25. `scripts/link_manager.py`
26. INIT.md for project linking
27. Voice file system

### Phase 7 — CDP Watcher
28. `scripts/browser_server.py`
29. Watcher dispatch pattern
30. `server ps` / `server kill`
31. Platform auto-start (LaunchAgent / scheduled task / systemd)

### Phase 8 — Optional add-ons
32. Setup wizard
33. Video intelligence
34. Question monitor
35. Mapping skill framework
36. Refined knowledge dashboard API

## Lines of Code Budget (approximate, for scoping)

| Subsystem | Approximate LOC |
|-----------|-----------------|
| CLI dispatcher | ~2000 |
| Cache/context/sync/indexer/config managers | ~2500 |
| RAG (engine + chunker + indexers + bridge) | ~1500 |
| Graph (builder + analyzer + exporter + diff + tree-sitter) | ~2000 |
| Providers (4 × ~500 each) | ~2000 |
| Skills framework + domain skills | ~2000 |
| Playwright skills | ~1500 |
| CDP watcher + dispatch | ~800 |
| Dashboard (server + HTML + JS) | ~1500 |
| Setup wizard + install.py | ~2500 |
| Tests | ~4000 |
| **Total** | **~22,000** |

This compares to ~10,000 LOC for the original after generalization. The open-source version will be larger because provider adapters replace hardcoded implementations.
