# Project Extraction — Open-Source Blueprint

This directory is a **reconstruction blueprint** for the AI-optimized multi-repository knowledge system that was developed internally. Every file here is written so the project can be rebuilt from scratch as an open-source tool, with **no organization-specific** code, URLs, repositories, credentials, or data.

All external systems (issue trackers, source control, log search, wikis) are described as **pluggable providers** behind abstract interfaces. The reference implementation ships one concrete adapter per provider family; swapping adapters (JIRA→Linear, GitLab→GitHub, Splunk→Elasticsearch, Confluence→Notion) is the intended extension path.

---

## How To Use This Blueprint

1. Read `00-overview/vision.md` to understand **what** is being built and **why**.
2. Read `01-architecture/` to understand the layering.
3. Use `02-cli/` through `08-data-models/` as the implementation spec — each file describes a subsystem in enough detail that it can be built without referencing the original codebase.
4. `09-ai-integration/` covers how AI assistants (Claude Code, Copilot, Cursor) plug in.
5. `10-ideas-roadmap/` captures ideas and future work.

You do **not** need to build everything at once. The system is layered — a minimal useful version is: context + cache + one provider + CLI + RAG.

---

## Top-Level Directory Map

| Directory | Contents |
|-----------|----------|
| `00-overview/` | Vision, pitch, naming, licensing |
| `01-architecture/` | Multi-context model, directory layout, data flow |
| `02-cli/` | CLI command surface, dispatch pattern |
| `03-install-setup/` | Installer, setup wizard, config system, sandbox workarounds |
| `04-providers/` | Pluggable provider contracts (issue tracker, source control, log search, wiki, itsm, cloud logs, CI/CD) |
| `05-modules/` | Core engines: RAG, knowledge graph, cache, sync, indexer, dashboard, CDP/watcher |
| `06-skills/` | Skills framework + per-skill blueprints (domain skills, API skills, browser/Playwright skills) |
| `07-tests/` | Test strategy + per-test blueprints |
| `08-data-models/` | Cache file schemas, graph schema, index shapes |
| `09-ai-integration/` | CLAUDE.md pattern, Claude Code slash-command skills, project linking |
| `10-ideas-roadmap/` | Original ideas, new ideas, what's next |

---

## Naming

The extraction preserves the project name only in the blueprint’s historical notes; when rebuilding as open source, pick a new name. Examples used throughout: `tool`, `the system`, or `knowledge-os` as a placeholder. Replace globally.

---

## What's Intentionally Excluded

- Any authenticated or proprietary data
- Internal hostnames, log-search index names, issue-tracker project keys, wiki space keys
- Real tokens, auth URLs, SSO endpoints
- Any product / team / organization names
- Any domain-specific knowledge content (entity types, field mappings, enum translations, scenarios)
- Compiled caches and indexes (`cache/`, `chromadb/`, `contexts/*/repositories/`)
- Vendor certificate bundles

Everything excluded has an **extension point** described in the blueprint where an adopter plugs in their own equivalent.
