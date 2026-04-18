# Ideas & Roadmap

Captures the ideas that shaped this project — both the original open-source seed and the new ideas layered on during internal use — plus what's worth building next.

---

## Original Ideas (carry over verbatim)

These were in the original seed project and remain the backbone of the system:

1. **Multi-repo caching with minimal tokens.** Index every repo as a small JSON summary (structure, APIs, dependencies) so an AI can reason across an ecosystem without loading source.
2. **Semantic search via RAG** over the combined corpus (repos, issues, wiki, commits).
3. **Setup wizard** for interactive provisioning of new ecosystems.
4. **Web dashboard** for exploring what's cached.
5. **Voice/personality system** — the tool can speak in a defined persona. Any voice file drops in; the default ships neutral.
6. **SCM walker** — crawl a source-control group recursively to discover all repos.
7. **Bulk issue cacher** — populate an ML-friendly local cache of issue data for offline search and historical analysis.
8. **JSON caches designed for AI** — every cache file is self-describing, token-efficient, and readable by AI assistants without invoking the tool.
9. **Skills system** — pluggable capabilities with a consistent `execute(action, **kwargs)` interface.
10. **Project linking** — one command to register a project with Claude Code + Copilot + Cursor.
11. **Browser SSO** via Playwright — one sign-in covers many providers (issue tracker, source control, wiki, log search).
12. **OAuth2 token bridge** — a local port that hands out current tokens to local tools.
13. **Symlink-based integration** (`_<tool>/`) — any project can symlink into the tool to get its capabilities.

---

## New Ideas (added during internal use)

Ideas that emerged from real-world use, worth preserving in the rebuild:

### Architecture

- **Contexts (multi-tenancy).** A single installation hosts N isolated ecosystems. Each has its own repos, caches, RAG, graph, config. This turned out to be the most valuable single feature.
- **Known-context templates.** Pre-configured ecosystems with `definition.toml`, `CLAUDE.md`, per-context skills, and domain knowledge. A one-command provision for recurring deployments.
- **Post-sync hooks.** Per-repo processors that run after sync. Extension point for things like regenerating slash commands from docs-template repos.
- **Auto-RAG-rebuild toggle.** Sync does NOT rebuild RAG unless configured — preventing accidentally long sync cycles.

### CDP Watcher / Dispatch

- **Watcher process** outside the AI sandbox that owns the browser + keychain; sandbox-bound CLI dispatches requests to it via files. Solves the "Claude sandbox can't auth" problem cleanly.
- **`server ps` / `server kill`** as sandbox-safe replacements for bare `ps`/`kill`, which are blocked in many AI harnesses.
- **macOS LaunchAgent / Windows scheduled task / Linux systemd user unit** to auto-start the watcher on login.

### Knowledge Graph

- **Full knowledge graph** (repos → packages → classes → methods → APIs → dependencies) built from caches + AST. NetworkX under the hood.
- **God-node analysis** via combined centrality metrics.
- **Community detection** (Leiden → Louvain → label-propagation fallback).
- **Surprising-connections** — cross-community edges flagged for review.
- **Suggested-investigations** — ambiguous-edge surfacing.
- **vis.js interactive visualization** with community coloring, search, filter.
- **Graph diffs** — structural change tracking between builds.
- **Graph↔RAG bridge** — god-node importance boosts RAG relevance scores.

### Embedding Backend Fallback Chain

- **ONNX + CoreML (macOS arm64) → MPS → CPU** — 10-20x speedup on Apple Silicon; graceful fallback.
- **Embedding backend as a pluggable interface** — easy to swap for OpenAI, Cohere, or a local OpenAI-compatible server.

### Video Intelligence

- **Video → markdown intelligence chunks** via transcription + LLM extraction, auto-picked-up by RAG.
- **Video → PPTX/DOCX** conversion with keyframe extraction and cross-video deduplication.
- **MLX-Whisper → faster-whisper fallback** — Apple Silicon accelerated, CPU fallback.
- **MLX-LM → Ollama fallback** — same idea for the LLM.

### Cross-System Trace

- **`logs lifecycle <event_id>`** — walk a distributed event across multiple log indexes, joining by correlation IDs. Per-service traversal rules configured per context (which indexes to hop through, which field is the join key).
- **Log-search playbook** — baked-in help content explaining how to investigate common issues in the log backend.

### MR/PR Automation

- **`mr-read`** reads MR metadata, approvals, pipelines, and review threads via REST — no browser needed. Key for AI assistants babysitting PRs.
- **Standard MR description format** encoded as a Claude Code skill per context.

### Question Monitor

- **Background daemon** that tracks posted questions (comments with ?) on issue-tracker tickets and alerts when someone answers. Turns async-question handoffs from lossy back into closed-loop.

### Cross-Context RAG

- **`rag search-all`** queries every context's RAG and merges results with context-source tags. Useful for platform-level questions that span product lines.

### Corporate-Environment Hardening

- **Single-file cert propagation** — one `netscope.pem` file sets `GIT_SSL_CAINFO`, `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE`, `CURL_CA_BUNDLE`, `NODE_EXTRA_CA_CERTS` etc. for every subprocess. Solves 95% of "SSL: CERTIFICATE_VERIFY_FAILED" cases.
- **File-based git credentials** (`.git-credentials`) instead of the keychain — works from AI sandboxes uniformly.
- **PyPI mirror fallback** for corporate proxies that intercept TLS.
- **Edge preferred on Windows** for Windows Integrated Auth / Kerberos delegation.

### Auth Hardening

- **Typed exceptions** (`AuthenticationError`, `ApiRequestError`) with actionable messages carrying the URL, method, and the command to run outside the sandbox.
- **Per-environment token cache** keyed by `client_id@hostname@env`.
- **Auto-refresh on 401** with single retry (not infinite) — if the refresh also fails, raise the typed error.

### Dashboard Extensions

- **Refined knowledge API** (`/api/contexts/<ctx>/refined/...`) — lets a context ship its own domain-specific data views (field explorer, correlation matrices, enum maps).
- **Per-context dashboard templates** — each context can inject its own HTML under `contexts/<ctx>/dashboard/`.

### AI Integration Depth

- **CLAUDE.md-pattern layering** — authoritative + detail pages + per-context overrides. Prevents the main file from ballooning.
- **INIT.md for linking** — AI-readable bootstrap instructions for linking the tool into other projects.
- **Repo-post-sync generating Claude Code skills** — slash commands regenerated automatically when a docs-template repo changes.

---

## What's Worth Building Next

These didn't make it into the internal version but are the natural next steps.

### Providers

- [ ] **GitHub adapters** (issues + SCM + Actions) — likely the most impactful immediate add for OSS.
- [ ] **Linear adapter** — covers the "modern JIRA alternative" case.
- [ ] **Notion adapter** — completes the wiki story.
- [ ] **Markdown-folder wiki adapter** — zero-friction starter for new users.
- [ ] **OpenSearch / Elastic adapter** for log search.
- [ ] **Grafana Loki adapter**.
- [ ] **Azure DevOps** (Boards + Repos + Pipelines) bundle.

### Core

- [ ] **Vector store abstraction** — swap ChromaDB for Qdrant, pgvector, Weaviate, FAISS. Interface is already close; just need to formalize.
- [ ] **Embedding backend plug-ins**: OpenAI, Cohere, Voyage, local OpenAI-compatible servers.
- [ ] **Incremental graph build** — only re-extract changed repos since last build. Currently rebuilds from scratch.
- [ ] **Incremental RAG** — partial-update instead of full re-embed. Hash index exists; just need to wire it.
- [ ] **Scheduled sync** — a cron-like scheduler so the tool keeps caches fresh without user intervention. Hook into OS-native schedulers (launchd, Task Scheduler, systemd timers).

### Dashboard

- [ ] **Real-time sync progress** via SSE or WebSocket.
- [ ] **Search UI** — semantic search directly from the dashboard without dropping to CLI.
- [ ] **Per-context health scoring** — flag stale caches, missing auth, config drift.
- [ ] **Inline graph navigation** — click a node, see related issues / wiki pages.

### Developer Experience

- [ ] **`<tool> doctor`** — one command that runs every self-check (venv health, cert propagation, provider auth status, cache freshness, Playwright install) and prints actionable fixes.
- [ ] **`<tool> init <adapter>`** — scaffold a new provider adapter from a template.
- [ ] **Plugin packaging** — publish adapters as pip packages; auto-discover on install.
- [ ] **Homebrew formula / Scoop manifest / AUR package** — single-command install on each platform.

### AI Integration

- [ ] **MCP (Model Context Protocol) server** — expose the tool as an MCP server so any compatible assistant (not just Claude Code) gets cache + RAG + graph access as tools.
- [ ] **Multi-assistant broker** — one config describing all linked projects and AI tools; the registry updates each tool's config from a single source.
- [ ] **Slash-command registry across tools** — write a skill once, install to Claude Code + Cursor + Copilot.

### Governance

- [ ] **Audit log** — every provider call recorded with who / when / which context / what bytes. Enables compliance review.
- [ ] **Policy gates** — deny-by-default for write operations on specific providers/contexts.
- [ ] **Content redaction** — scrub known-sensitive patterns (PII, secrets) before caching. Works in concert with the data-caching policy.

### Quality of Life

- [ ] **`<tool> watch`** — hot-reload sync as repos change locally. Useful for active development on local copies.
- [ ] **`<tool> snapshot` / `restore`** — point-in-time backup/restore of a context's caches.
- [ ] **Colorized / structured log output** with a `--json` flag for piping into tooling.
- [ ] **Progress bars for long commands** — the install progress file pattern extended to sync, RAG build, graph build.
- [ ] **TUI dashboard** (textual / rich) — for users who live in a terminal.

### Security

- [ ] **Signed known-context bundles** — supply-chain protection for shared templates.
- [ ] **Secret-in-config linter** — refuse to commit known-secret patterns to context.ini.
- [ ] **Ephemeral token handling audit** — assert no token leaks outside `.auth/`.

---

## Philosophical Tenets (don't break these)

When making changes, re-read these:

1. **CLI is the API.** If a feature isn't CLI-invokable, it doesn't exist.
2. **Caches are files.** If you're tempted to add a database, you're solving the wrong problem.
3. **Providers are swappable.** If a decision bakes in a specific vendor, reject it and go behind an interface.
4. **Auth never lives in the sandbox.** The sandbox consumes tokens, doesn't fetch them.
5. **Skills are the extension primitive.** If you want to add a capability, write a skill.
6. **Contexts isolate.** Never cross-contaminate.
7. **AI assistants are first-class users.** Design as if an AI is the primary operator.
8. **Fail loud.** Tell the user what to run; don't retry forever.
9. **Don't persist what you can re-derive.** Rebuild RAG from caches. Rebuild graphs from AST. Rebuild indexes from repos.
10. **Prefer generic over clever.** A boring provider adapter beats a clever one you can't swap.
