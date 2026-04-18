# Vision

## The Problem

Modern organizations are fragmented across dozens of repositories, an issue tracker, a wiki, a log search engine, CI/CD pipelines, cloud dashboards, and backend APIs. Engineers and AI assistants both waste most of their cognitive budget **finding the right surface to ask**, rather than doing the work.

AI coding assistants amplify this: they're excellent inside a single repo, but blind across the ecosystem. A question like *"how does feature X work end-to-end?"* requires jumping between a frontend repo, a backend repo, a gateway, a queue consumer, a database schema, an issue tracker ticket, a runbook in the wiki, and yesterday's error logs. No one of those systems is the authoritative surface.

## The Thesis

Build a **per-team knowledge substrate** that:

1. **Indexes the whole ecosystem locally** — every repo, every issue, every wiki page, every API schema.
2. **Speaks one CLI** — so humans and AIs query via the same surface.
3. **Serves AI assistants directly** — via a slash-command interface (Claude Code, Copilot, Cursor) and a structured cache layer they can read without running the tool.
4. **Treats external systems as pluggable providers** — issue tracker, source control, log search, wiki, CI/CD, cloud logs, ITSM are all interfaces, not hard dependencies.
5. **Isolates ecosystems into contexts** — one installation can host multiple independent teams/products without their caches colliding.
6. **Persists structured knowledge**, not raw dumps — JSON caches, a RAG vector index, and a knowledge graph, each optimized for a different query mode.

## What's Different

Other "code assistant context" tools either:
- Index a single repository (Sourcegraph, GitHub Copilot workspace)
- Live inside one provider (JIRA AI, GitLab Duo)
- Require sending all your code to a hosted service

This tool is **local-first**, **multi-system**, **multi-context**, and **provider-agnostic**. The intelligence is in the orchestration, not the model.

## Design Principles

1. **CLI is the API.** Every capability is reachable from `tool <cmd>`. AI assistants call the CLI; humans call the CLI; the dashboard calls the CLI. No second surface.
2. **Caches are files, not databases.** Everything persistable is a JSON or markdown file on disk, readable without running the tool. RAG/graph stores are rebuildable from the caches.
3. **Providers are swappable.** Any real dependency on a vendor (JIRA, GitLab, Splunk, Confluence) is mediated through a small interface. Swap JIRA→Linear by writing one adapter.
4. **Auth never lives in the sandbox.** Token acquisition is a separate process (watcher/CDP); the main tool consumes tokens, it doesn't fetch them. This keeps the main tool safe to run in locked-down AI harnesses.
5. **Skills are the extension primitive.** A "skill" is a self-contained capability (domain logic, API client, browser scraper) with a consistent interface. Adding a new provider = writing a new skill.
6. **Contexts isolate ecosystems.** A single installation hosts N contexts; each has its own repos, caches, JIRA data, wiki data, RAG index. No cross-pollination unless explicitly requested.
7. **AI assistants are first-class users.** The tool ships `CLAUDE.md` templates, slash commands, and instruction files for Claude Code, Copilot, and Cursor. Installing = linking into each AI tool.
8. **Fail loud, not fallback silent.** If auth fails, the tool stops and tells the user what to run. It does not try to re-acquire tokens from inside the sandbox, it does not retry forever.

## Non-Goals

- Hosting anyone's code on a server.
- Competing with full IDEs.
- Replacing the issue tracker / wiki / log search. This tool *wraps* them.
- Being a real-time sync daemon. Sync is explicit, scheduled, or on-demand.
- Handling write operations on production data without an explicit command.

## Target User

A platform engineer or senior developer working across 10–200 repositories, who uses an AI coding assistant daily, who is tired of copy-pasting context between tools, and who wants the AI to *already know* about their ecosystem without having to explain it each time.
