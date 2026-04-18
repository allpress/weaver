# CLI Command Surface

The CLI is the primary interface. Everything in the system is reachable from `<tool> <cmd>`.

## Dispatch Pattern

- Single `<tool>.py` entry point.
- Dispatch by direct `if cmd == "..."` on `sys.argv[1]`, with nested subcommand handling. (Can be refactored to argparse; the original used manual dispatch for fine-grained error messages.)
- Global flags (`--context`, `--env`, `--visible`, `--headless`, `--time`, `--limit`, `--force`) are parsed inline by each command.
- Commands that need a provider call through the skill manager (`skill_manager.execute_skill(name, action=..., **kwargs)`).

## Command Families

Top-level commands group by domain. Every domain has a consistent sub-pattern: `<domain> <action> [args]`.

| Family | Purpose |
|--------|---------|
| `context` | Manage isolated ecosystems |
| `clone` / `pull` / `recache` / `unshallow` / `cache` | Repository lifecycle |
| `sync` | Unified refresh across all sources |
| `query` | Structured cache inspection (JSON output) |
| `rag` | Semantic search and RAG index management |
| `skill` | Generic skill invoker |
| `logs` | Log search provider interface |
| `issues` (was `jira`) | Issue-tracker provider interface |
| `code` / `scm` (was `gitlab`) | Source-control provider interface |
| `wiki` (was `confluence`) | Wiki provider interface |
| `itsm` (was `servicenow`) | Ticketing/ITSM provider interface |
| `cloud-logs` (was `cloudwatch`) | Cloud log provider interface |
| `auth` | Token acquisition (OAuth2, SSO) |
| `env` | Environment switching (prod/staging/test/dev or custom) |
| `api` | Backend API access (generic domain APIs) |
| `lookup` | Domain entity lookup (extension point — adopter defines entity types) |
| `access` | Authorization analysis |
| `jira-cache` / `wiki-cache` | Bulk provider caching |
| `external` | On-demand external repo management |
| `setup` / `wizard` / `initialize` | Interactive setup |
| `server` | CDP/browser watcher and sandbox-safe process management |
| `dashboard` | Web dashboard |
| `report` | PDF/DOCX/PPTX/video generation |
| `link` | Register with AI tools (Claude Code, Copilot) |
| `claude-skills` | Manage Claude Code slash commands |
| `graph` | Knowledge graph build/analyze/export/diff |
| `export` / `cache export` / `cache import` | Context bundle export/import |
| `migrate` / `check` / `syscheck` / `status` | Utilities |
| `monitor` | Question-tracking daemon |
| `mapper` / `refine` | Domain data mapping utilities (extension point) |

---

## Detailed Catalog

### Context Management

```
<tool> context <subcommand>
```

| Subcommand | Args | Purpose |
|------------|------|---------|
| (none) | | Show context help |
| `list` | | List all contexts |
| `current` | | Show active context + metadata |
| `use` | `<name>` | Switch active context |
| `create` | `<name> [--description "..."] [--issues P1,P2] [--log-services s1,s2]` | Create new context |
| `info` | `<name>` | Show details, repos, issue count, wiki count, RAG counts |
| `delete` | `<name>` | Delete (confirmation required) |
| `research` | `<name> [--auto-init] [--description ...]` | Auto-discover repos/issues/wiki in context |
| `<name> <cmd>` | `[args...]` | Run command in context scope without switching |

**Cross-cutting flag**: `--context <name>` works on most commands.

### Repository Management

| Command | Purpose | Flags |
|---------|---------|-------|
| `clone` | Clone all configured repos | `--force` |
| `pull` | Update all repos | |
| `recache` | Pull + regenerate caches | |
| `unshallow` | Convert shallow clones to full history | |
| `cache [repo]` | Regenerate JSON caches (all or specific) | |

### Unified Sync

```
<tool> sync [--all] [--issues] [--wiki] [--rag] [--full] [--status] [--context <name>]
```

| Flag | Effect |
|------|--------|
| `--all` | Repos + issues + wiki + RAG (full) |
| `--issues` | Include issue tracker sync |
| `--wiki` | Include wiki sync |
| `--rag` | Rebuild RAG after sync |
| `--full` | Full rebuild (vs incremental) |
| `--status` | Show freshness report only |

### Query (Cache Inspection — JSON API)

```
<tool> query <subcommand>
```

| Subcommand | Purpose |
|------------|---------|
| `status` | Cache overview (repo count, file count, API count) |
| `repos` | List cached repositories |
| `apis [repo]` | All API endpoints (all or one repo) |
| `search <term>` | Full-text cache search |
| `repo <name>` | Single-repo summary |
| `detail <name> [section]` | Sections: `apis`, `structure`, `build`, `files`, `all` |
| `overview` | Human-readable overview |

### RAG

```
<tool> rag <subcommand> [options]
```

| Subcommand | Purpose | Flags |
|------------|---------|-------|
| `search <query>` | Semantic search | `-n <count>`, `--cross-context` |
| `search-all <query>` | Shorthand for `--cross-context` | |
| `context <topic>` | Formatted context for LLM | `--cross-context` |
| `stats` | Index statistics | `--cross-context` |
| `index --rebuild` | Rebuild index | `--full` |

### Skills (Generic Invoker)

```
<tool> skill <skill_name> <action> [--option value ...]
```

Registered skill names (provider-agnostic):
- `repository_query` (list, get, search)
- `codebase_analysis` (dependencies, structure)
- `log_search_url`, `log_search_query`, `log_analysis` (swappable with provider)
- `issue_tracker` (get, my_issues, analyze_defect)
- `scm` / `source_control` (project/file/clone ops)
- `playwright` (browser automation)
- `voice_manager`
- `access` (authorization model)
- `api_skills` (generic REST API adapters)

### Logs (Log-Search Provider)

```
<tool> logs <subcommand> [--options]
```

| Subcommand | Purpose | Args |
|------------|---------|------|
| `auth` / `check` | SSO auth + auth-status | |
| `search` | Structured search | `<service> <env> [--search term] [--level L] [--time range]` |
| `errors` | Error/warning summary | `<service> <env> [--time 1h]` |
| `analyze` | Pattern analysis + health | `<service> <env>` |
| `correlate` | Cross-service correlation | `<svc1,svc2> <env> [--key field]` |
| `trace` | Trace event across services | `<trace_id> <svcs> <env>` |
| `report` | Error report all services | `[env] [--time 24h]` |
| `indexes` | List accessible indexes (extension point) | |
| `playbook [topic]` | Investigation playbook | topic ∈ overview / indexes / sources / queries / auth / pitfalls / reference |

**Extension-point subcommands** (name them after the domain signals they track):
- Generic **traversal subcommands** — e.g. `upstream <id>`, `downstream <id>`, `lifecycle <id>` — each configurable per context. Each maps a logical event ID to a search query pattern for a specific log index.

### Issues (Issue-Tracker Provider)

```
<tool> issues <subcommand>
```

| Subcommand | Purpose | Args |
|------------|---------|------|
| `auth` / `check` | SSO auth | |
| `me` | Your assigned issues | `[--status open\|in_progress\|done\|all]` |
| `get` | Full details | `<KEY>` |
| `analyze` | Deep defect analysis (code correlation) | `<KEY>` |
| `plan` | Story implementation plan | `<KEY>` |
| `search` | Query search | `"<JQL-equivalent>"` |
| `comment` | Add comment (ADF/rich-text aware) | `<KEY> "<message>"` |
| `attach` | Attach file | `<KEY> <file> ["comment"]` |
| `create` | Create issue | `--summary --type --project --epic --description --priority --link-type --link-issue [--team <name>]` |
| `ask` | Post AI-generated clarifying questions | `<KEY>` |
| `wiki` | Fetch linked wiki content | `<URL>` |

**Link types**: use provider's native vocabulary; expose as config (not hardcoded).

### Code (Source-Control Provider)

```
<tool> code <subcommand>   (alias: scm)
```

| Subcommand | Purpose |
|------------|---------|
| `auth` / `check` | SSO |
| `search <query> [--visible]` | Project search |
| `list [group]` | List projects |
| `groups [search]` | List groups/orgs |
| `project <path>` | Project details |
| `browse <path> [dir]` | Browse tree |
| `get <path> <file>` | Fetch file contents |
| `clone <path> [branch]` | Clone to cache |
| `add-config <url>` | Add to repo config |
| `walk <group_url>` | Recursive group traversal |
| `token` | Personal access token management |
| `mr` / `pr` | Create merge/pull request |
| `mr-read` | Read MR/PR metadata, approvals, pipelines, threads |

### Auth

```
<tool> auth <subcommand>
```

| Subcommand | Purpose |
|------------|---------|
| `login` | Acquire OAuth2 token via browser SSO |
| `status` | Check token validity + SSO session |

Tokens are **environment-specific** (run `env` first).

### Environment

```
<tool> env <name>
```

Environments are fully configurable per context. Defaults shipped in the skeleton: `prod`, `staging`, `test`, `dev`. Each env maps to a dict of service base URLs in context config.

### API Access (Generic REST Adapters)

```
<tool> api <subcommand> [--env environment]
```

| Subcommand | Purpose |
|------------|---------|
| `env <name>` | Switch |
| `status` | Show current env + service URLs |
| Everything else | Delegated to named API skills (domain extension point) |

### Data Lookups (Domain Extension Point)

```
<tool> <entity> <action>   # entity names defined by the adopter per context
```

Entity names are defined in context config. Each maps to a pluggable adapter. The skeleton ships no real entities; it ships a **template adapter** (`scripts/api_skills/template_entity_api.py`) and a `domain_knowledge.py` extension hook.

### Access Control

```
<tool> access <subcommand>
```

| Subcommand | Purpose |
|------------|---------|
| `build` | (Re)build access model |
| `compare [service]` | Compare authority configs across envs |
| `analyze <user> <service> <endpoint> [env]` | 403-diagnosis |
| `users <group>` | List users in AD/IdP group |
| `whocan <user>` | Endpoints accessible to user |
| `endpoint <service> <path>` | Auth requirements for endpoint |

### Provider Bulk Caches

```
<tool> issue-cache <subcommand>
<tool> wiki-cache <subcommand>
```

Both follow the same shape: `status`, `build` (all), `update` (incremental), `get <id>`, `search`, `stats`, `export`, `cache-all <scope>`.

### External Repos

```
<tool> external <subcommand>
```

| Subcommand | Purpose |
|------------|---------|
| `list` | Known externals |
| `enable <path>` | Activate in config |
| `disable <path>` | Comment out |
| `clone <path>` | Clone + cache |
| `discover "<query>"` | Search SCM and add |

### Setup / Wizard

```
<tool> setup [--known <name>] [--from-file <config.json>] [--from-template <name>]
```

### Server (CDP / Watcher / Process Management)

```
<tool> server <subcommand>
```

| Subcommand | Purpose |
|------------|---------|
| `start [--port N] [--foreground]` | Headless browser for CDP |
| `stop` | Terminate |
| `status` | Running? |
| `diagnose` | Deep check + auto-repair |
| `ps [pattern]` | List processes (sandbox-safe replacement for `ps`) |
| `kill <pid\|pattern> [-9]` | Kill (sandbox-safe replacement for `kill`) |
| `watch` | Start foreground watcher |
| `dispatch <command> [--arg v ...]` | Send command to watcher |

The `watch` + `dispatch` pair is how the sandboxed CLI delegates operations that need keychain/browser access to a process outside the sandbox. See `05-modules/cdp-watcher.md`.

### Dashboard

```
<tool> dashboard
```

Starts the web UI on `http://localhost:4242`. See `05-modules/dashboard.md`.

### Reports

```
<tool> report <file.md> [output]
```

Supports `--docx`, `--ppt`, `--video [--audio]`, `--transcribe`.

### Project Linking

```
<tool> link <subcommand>
```

| Subcommand | Purpose |
|------------|---------|
| `list` / `status` | Show linked dirs |
| `sync` | Re-sync registry to AI tool configs |
| `self` | Register the tool itself |
| `remove <path>` | Unlink |
| (default) `<path> [--init]` | Link a project |

### Claude Code Skills

```
<tool> claude-skills <subcommand>
```

| Subcommand | Purpose |
|------------|---------|
| `list` | Available |
| `installed` | Installed |
| `install [name]` | Install (all or named) |
| `uninstall <name>` | |
| `sync` | Sync all |
| `status` | Install status |

### Knowledge Graph

```
<tool> graph <subcommand> [--context <name>] [--no-treesitter] [--deps]
```

| Subcommand | Purpose |
|------------|---------|
| `build [--deps]` | Build graph |
| `analyze` | God nodes, communities, surprises, suggestions |
| `export [--format all\|html\|graphml\|cypher\|json\|report] [--output dir]` | Export |
| `diff [path1] [path2]` | Diff snapshots |

**Node types**: `repo`, `package`, `class`, `method`, `function`, `interface`, `enum`, `constant`, `api_endpoint`, `dependency`.
**Edge types**: `contains`, `exposes`, `imports`, `extends`, `implements`, `calls`, `references`, `uses`, `depends_on`.

### Export / Import

```
<tool> export <subcommand>
<tool> cache export|import
```

| Subcommand | Purpose |
|------------|---------|
| `export <context>` | `.tar.gz` archive (respect `--no-rag --no-issues --no-wiki`) |
| `export all` | Every populated context |
| `export list [--output dir]` | Available archives |
| `export inspect <file>` | Manifest |
| `export import <file> [--merge] [--name newname]` | Import |

### Utilities

| Command | Purpose |
|---------|---------|
| `migrate [--dry-run]` | Migrate to multi-context layout |
| `check` / `syscheck` | System requirements check |
| `status` | Cache overview |
| `specification-commands generate [--dispatch]` | (Extension hook) regenerate Claude Code commands from repo artifacts |
| `mapper` | Domain field mapping (extension point) |
| `refine` | Refinement utilities (extension point) |

### Monitor

```
<tool> monitor <subcommand>
```

Background daemon that tracks posted questions on an issue tracker and alerts when answered. Subcommands: `start`, `stop`, `status`, `check`, `list [--status pending\|answered\|expired]`, `config [--interval 60]`, `remove <id>`.

---

## Cross-Cutting Flags

| Flag | Scope |
|------|-------|
| `--context <name>` | Override active context |
| `--env <env>` | Override active environment |
| `--visible` | Show browser window (Playwright) |
| `--headless` | Hide browser |
| `--time <range>` | Time range (5m, 1h, 24h, -7d, ISO) for log queries |
| `--limit <n>` | Result cap |
| `--force` | Skip confirmations |

---

## Generalization Notes

Items that existed as hardcoded values in the original and **must be externalized** in the open-source rebuild:

1. **Environment names and URLs** — move to context config.
2. **Service names** — any hardcoded service identifiers must be made configurable per context.
3. **Issue tracker / wiki space / project keys** — per-context config.
4. **IdP group naming conventions** — pluggable prefix/pattern.
5. **Domain entity schemas** — extension points. Adopters define their own entity types and ship a template adapter in `scripts/api_skills/`.
6. **SSO hostnames** — per-context.
7. **Cross-system lifecycle traces** — configurable traversal subcommands defined per context (`[log_lifecycle]` INI section describing indexes + join keys).

---

## Minimum Viable CLI

To ship a usable v0, implement:
1. `setup`, `context` (list/use/create)
2. `clone`, `pull`, `cache`
3. `query` (status, repos, apis, search)
4. `rag` (search, index, stats)
5. `sync`
6. `server` (start/stop/status)
7. `auth` (login/status)
8. One provider family (e.g., `issues` or `code`)
9. `link`, `claude-skills`
10. `graph build|analyze|export`

Everything else is additive.
