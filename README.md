# Weaver

> The aggregator. Weaves context — code, docs, issues, wikis — into a bridged RAG + knowledge graph agents can query through one surface.

**Weaver** is a bidirectional context-weaving engine for AI agents. It ingests source code, docs, issue trackers, wikis, and APIs into a per-team knowledge substrate: a bridged RAG vector index and directed code graph that agents can query in one surface.

> **Status:** Pre-alpha. Backbone shipped; providers and parsers beyond the first tranche are in progress.

## What Weaver does

- **Ingests** providers (GitLab today; JIRA / Confluence / GitHub / Splunk next)
- **Parses** arbitrary sources through a pinned per-format parser family (Markdown, HTML, PDF, DOCX, source code via tree-sitter, …)
- **Weaves** a bridged RAG+graph: RAG over docs + knowledge graph over code, with results reranked by graph centrality
- **Serves** via CLI, intended to be called by humans and AI assistants alike (Claude Code slash commands ship in `commands/`)

## Quickstart

```bash
pip install -e .[dev]

# 1. Create a context (isolated knowledge domain) and point it at GitLab
weaver context create team-platform \
    --display-name "Platform Team" \
    --source-control-base-url https://gitlab.example.com \
    --source-control-group platform

# 2. Store the GitLab token (prompts hidden; never via --value)
weaver secret set gitlab token --context team-platform

# 3. Clone every repo in the group, build RAG + code graph
weaver clone gitlab --context team-platform

# 4. Ask something
weaver rag query --context team-platform --bridge "how does auth work end-to-end?"
```

## Layout

```
weaver/                           # Python package
  auth/                         # SecretStore + AuthResolver + precedence chain
  parsers/                      # Pluggable parsers (per-format canonical libs)
  providers/                    # Pluggable providers (GitLab, JIRA, …)
  rag/                          # ChromaDB engine + doc indexer
  graph/                        # tree-sitter + NetworkX code graph
  skills/                       # Skill framework + codebase-derived generator
  cli/                          # click commands
commands/                       # Claude Code slash commands (symlink into projects)
contexts/                       # per-context isolated data (gitignored)
_config/                        # global config + templates
extraction/                     # authoritative spec
docs/                           # human-facing docs
tests/                          # pytest suite
```

## The auth precedence chain

Every provider uses the same resolver, in this fixed order:

1. Env var override
2. User-issued API token
3. Cached OAuth access token (if still valid)
4. OAuth refresh → access
5. Basic auth
6. Interactive OAuth helper (TTY only)
7. **Playwright scrape** — last resort, requires `--dangerously-use-playwright-token` AND per-context opt-in AND per-call opt-in

See [extraction/04-providers/auth-and-secrets.md](extraction/04-providers/auth-and-secrets.md).

## Documentation

- [docs/specification.md](docs/specification.md) — what Weaver does, concepts, API surface
- [docs/architecture.md](docs/architecture.md) — internal layers
- [extraction/](extraction/) — full implementation blueprint (LOC-budgeted, phased)

## License

[Apache 2.0](LICENSE)
