# Installation, Setup Wizard, and Config System

Three interlocking subsystems:
1. `install.py` — bootstrap the environment (venv, deps, browsers, certs).
2. `scripts/setup_wizard.py` — interactive context provisioning.
3. `scripts/config.py` + `_config/` — config reading and known-context templating.

---

## 1. install.py (Bootstrap)

Self-contained Python script. Runs with the **system** Python, creates a venv, and installs everything else into it.

### Phases

| Phase | % | What |
|-------|----|------|
| **Prerequisites** | 5–10 | Python 3.10+ check (fatal on older), Git check (fatal if missing), corporate CA bundle detection (warn if missing), PyPI reachability test |
| **Venv** | 15–25 | Create `.venv/` (3 attempts, exponential backoff). Validate existing venv health. Upgrade pip. Auto-repair on corruption |
| **Dependencies** | 30–50 | Install core packages; optionally RAG (`--rag`), graph (`--graph`), accelerators. Stream pip output for large packages so users see progress. Retry per-package on transient errors |
| **Browsers** | 50–75 | Playwright browser install. Detect system browsers first (Chrome/Edge) — use those if found. Fall back to Playwright downloads. Handle sandbox EPERM and corporate-proxy 403 with actionable messages |
| **Package validation** | 55–65 | Import each core package in the venv to catch linking errors |
| **Embedding model pre-download** | 70 | (RAG only) Pull the default embedding model from HuggingFace (~90MB). Handles corporate proxies. Falls back to on-demand pull if blocked |
| **Browser CDP server setup** | 95 | Platform-specific auto-start: macOS LaunchAgent, Windows scheduled task, Linux systemd user unit. Opt-in — don't force this on users |

### Flags

```
python install.py             # full install
python install.py --check     # verify prerequisites, don't install
python install.py --repair    # nuke and rebuild venv
python install.py --playwright  # reinstall browsers only (for cert refresh)
python install.py --rag       # add RAG packages (chromadb, sentence-transformers)
python install.py --graph     # add graph packages (networkx, tree-sitter-*)
python install.py --rag-accel # add Apple Silicon accelerators (onnxruntime-silicon, optimum)
python install.py --graph-accel  # add Leiden community detection (graspologic)
```

### Certificate Propagation

If a corporate CA bundle is present (`netscope.pem` or equivalent — configurable filename), set these environment variables for every subprocess the installer spawns AND make sure the venv activate script sets them:

```
PIP_CERT
SSL_CERT_FILE
REQUESTS_CA_BUNDLE
GIT_SSL_CAINFO
CURL_CA_BUNDLE
NODE_EXTRA_CA_CERTS
WEBSOCKET_CLIENT_CA_BUNDLE
HTTPLIB2_CA_CERTS
```

This is the single most impactful decision for "it works behind corporate proxies" — most "SSL: CERTIFICATE_VERIFY_FAILED" errors come from a tool that isn't inheriting the cert. Setting all of them reliably solves 95% of real-world SSL issues.

### Sandbox-Safe Patterns

The installer might run under a restrictive AI-assistant sandbox. Known landmines and workarounds:

- **`.pem` reads denied** — if reading the cert path fails, assume it exists and that env vars are set by the parent. Don't crash.
- **`ps`/`kill` blocked** — provide equivalents via `<tool> server ps/kill`.
- **`/tmp` not writable** — use `$TMPDIR`.
- **Homebrew / apt / dnf invocations blocked** — fall back to prebuilt wheels via PyPI.
- **Unix socket access denied** — skip features that rely on Docker/SSH sockets; don't make them fatal.

### PyPI Mirror Fallback

If the default PyPI index fails (common behind TLS-inspecting proxies), fall back to a configured mirror. The mirror URL is configurable via `[install]` `pypi_mirror = ...` in `_config/defaults.ini`.

### Progress File

Write progress to `_PROGRESS_FILE` (JSON) after each phase:
```json
{"phase": "dependencies", "percent": 42, "message": "Installing chromadb...", "timestamp": "..."}
```
External tools (status-line widgets, dashboards) watch this file.

---

## 2. Setup Wizard

**Location**: `scripts/setup_wizard.py`. Invoked as `<tool> setup [--known <name>] [--from-file <json>] [--from-template <name>]`.

### Interactive Flow

1. **Prerequisites check** — verify install was successful. Offer `install.py` if not.
2. **Context selection**:
   - List known contexts from `_config/known_contexts/*/definition.toml`.
   - Choose a known context OR "custom".
   - If chosen context already exists, offer "keep as-is" / "update AI docs only" / "regenerate from scratch".
3. **Repository discovery** (custom only):
   - **Option A**: Group walk — point at a source-control group URL; the source-control skill walks it; user reviews the discovered list.
   - **Option B**: Manual paste — user pastes URLs one per line.
   - Save to `contexts/<name>/config/repositories/<name>.txt`.
4. **Issue-tracker config** (optional) — prompt for project keys, save to `[issues]` section.
5. **Log-search config** (optional) — prompt for service names / index mapping file.
6. **Wiki config** (optional) — prompt for space keys or start URLs.
7. **OAuth config** (optional) — prompt for client id / tenant id / scopes / API base URL.
8. **SSO auth** — detect existing shared browser profile; offer to auth if not already.
9. **Clone & index** — clone repos, run indexer, build cross-repo indexes.
10. **RAG build** (optional) — offer to build RAG now (requires `--rag` install flag).
11. **AI tool registration** — call `LinkManager.link_self()` to register with Claude Code + Copilot.

### Non-Interactive Modes

- `--known <name>`: load a known context template and provision without prompts.
- `--from-file config.json`: import a pre-authored config:
  ```json
  {
    "context_name": "myteam",
    "display_name": "My Team",
    "description": "...",
    "repositories": ["https://...", "https://..."],
    "issues": { "project_keys": ["PROJ"] },
    "wiki": { "start_urls": ["https://..."] },
    "log_search": { "services": ["svc1", "svc2"] },
    "oauth": { "client_id": "...", "tenant_id": "...", "api_base_url": "..." }
  }
  ```
- `--from-template <name>`: load from a template (alias for `--known`).

---

## 3. Config System

**Location**: `scripts/config.py`, `_config/`

### Hierarchy

1. **Global**: `_config/defaults.ini` — user-local settings.
2. **Global template**: `_config/defaults.ini.template` — shipped baseline (copy on first run).
3. **Known-context templates**: `_config/known_contexts/<name>/definition.toml`.
4. **Per-context**: `contexts/<name>/config/context.ini`.
5. **Env overrides**: `TOOL_*` environment variables override any matching key.

Reading: global → per-context → env, later wins.

### Global Config

```ini
[personality]
use_<tool>_voice = true
voice_file = voice/PRINCIPLED_VOICE.md

[cache]
parallel_workers = 4
cache_freshness_hours = 24

[ssl]
proxy_cert = netscope.pem          ; filename is configurable

[server]
auth_whitelist = *.your-sso.com,*.your-domain.com

[install]
pypi_mirror = https://pypi.org/simple
```

### Per-Context Config

```ini
[metadata]
display_name = My Team
description = ...
created_at = 2026-04-17T00:00:00Z
last_synced = 2026-04-17T10:00:00Z

[sync]
default_sources = repos,issues
full_sources = repos,issues,wiki,rag
issues_update_mode = incremental
issues_update_since = -1w
wiki_urls = https://wiki.example.com/space/TEAM
wiki_max_pages = 500
auto_rag_rebuild = true

[repositories]
groups = core,platform

[issues]
provider = jira                    ; or github, linear, azure_devops
projects = PROJ,INFRA

[wiki]
provider = confluence              ; or notion, markdown_folder
spaces = TEAM

[log_search]
provider = splunk                  ; or elastic, datadog
service_prefix = myteam-
services = svc1,svc2
mapping_dir = _config/log_search

[oauth]
provider = msal                    ; or generic
client_id = ...
tenant_id = ...
scopes = openid
api_base_url = https://api.example.com

[environments]
prod = https://api.example.com
staging = https://staging.api.example.com
test = https://test.api.example.com
dev = https://dev.api.example.com
```

### Known Context Definition (`definition.toml`)

```toml
[context]
name = "myteam"
display_name = "My Team"
description = "Microservices ecosystem for the Foo product line"

[repositories]
inline = [
    "https://gitlab.example.com/group/service-a.git",
    "https://gitlab.example.com/group/service-b.git,develop",
]

[repositories.external]
repos = ["group/optional-repo"]   # on-demand

[issues]
provider = "jira"
projects = ["MYTEAM"]

[wiki]
provider = "confluence"
spaces = ["TEAM"]

[log_search]
provider = "splunk"
config_file = "myteam.json"       # relative to _config/log_search/

[oauth]
client_id = "..."
tenant_id = "..."

[features]
issues = true
wiki = true
log_search = true
oauth = false
```

### Known-Context Layout

```
_config/known_contexts/<name>/
├── definition.toml             # REQUIRED
├── CLAUDE.md                   # REQUIRED — AI context reference
├── skills/                     # OPTIONAL — Claude Code skills
│   └── <skill-name>/
│       └── skill.md            # YAML frontmatter + body
├── knowledge/                  # OPTIONAL — domain knowledge (files are adopter-defined)
│   ├── index.json              # maps data types to knowledge files
│   └── <entity>.json           # adopter-defined data-type knowledge (tips, gotchas)
└── README.md                   # OPTIONAL — human-facing notes
```

### CLAUDE.md Required Sections (per-context)

- **Overview** — what this context covers
- **Repository Inventory** — table of repos + purposes
- **Architecture** — ASCII diagram of how systems connect
- **Domain Terminology** — glossary
- **Key Commands** — CLI one-liners relevant to this context
- **Related Contexts** — cross-references

Validation lives in `tests/test_known_contexts.py` — it enforces these sections exist with substantial content.

### LincAiConfig class (reference implementation)

```python
class ToolConfig:
    def __init__(self, config_path: Optional[Path] = None): ...
    def get(self, section: str, key: str, fallback=None) -> Any: ...
    # Common properties:
    use_voice: bool
    parallel_workers: int
    cache_freshness_hours: int
    default_context: str
    proxy_cert_path: Optional[Path]
    pypi_mirror: Optional[str]
    # Context helpers:
    def get_context_path(self, name: str) -> Path: ...
    def load_context_config(self, name: str) -> ContextConfig: ...
```

### Secrets Handling

Never persist in config files:
- OAuth tokens (live only in `_config/playwright/.auth/oauth_tokens.json`, gitignored, short-lived).
- API keys (read from env vars).
- Session cookies.

Config files in git: `_config/defaults.ini.template`, `_config/known_contexts/*/definition.toml`.
Config files NOT in git: `_config/defaults.ini` (user-local), `_config/playwright/.auth/`, `contexts/*/config/context.ini` (may contain OAuth client ids — arguably safe but still user-specific).

---

## 4. Linking Into Other Projects

After setup, a user typically wants to use the tool from inside other projects. Two mechanisms:

### Symlink (legacy)

```bash
ln -s /path/to/<tool> /path/to/project/_<tool>
```

Then the project's `CLAUDE.md` references `_<tool>/<tool>.py` commands.

### Registry (preferred)

```bash
<tool> link <project-path>            # register
<tool> link <project-path> --init     # register + write instruction files
<tool> link self                      # register the tool itself
<tool> link list
```

This writes to:
- Claude Code: `~/.claude/settings.json` → `permissions.additionalDirectories`.
- Copilot: VS Code user settings → `github.copilot.chat.codeGeneration.instructions`.
- Workspace: generates a multi-folder `.code-workspace` file.

No symlink needed. The project keeps its own CLAUDE.md with a section explaining how to invoke the tool from anywhere on disk.

See `09-ai-integration/ai-tools-integration.md` for the full linking contract.
