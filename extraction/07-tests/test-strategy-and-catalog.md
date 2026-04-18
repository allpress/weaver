# Test Strategy & Catalog

The test suite is the second-most-important deliverable (after the CLI). It encodes behavioral invariants that get lost in prose docs.

## pytest.ini

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -m "not oauth and not playwright"
markers =
    slow: slow-running tests (>2s)
    local: runs without network, OAuth, or Playwright
    oauth: requires a real OAuth token + network
    playwright: requires a real browser + SSO session
```

**Default run** excludes `oauth` and `playwright` markers so CI and local runs are fast and hermetic. Explicitly `pytest -m oauth` to run integration-auth tests; `pytest -m playwright` to run browser tests.

## Conftest Fixtures

**Location**: `tests/conftest.py`

```python
@pytest.fixture
def tmp_tool_dir(tmp_path):
    """Ephemeral tool-root with all expected directories and cert file."""
    # Creates:
    #   _config/repositories/
    #   _config/playwright/{.auth,chrome-profile}/
    #   cache/{repos,indexes,issues/items}/
    #   repositories/
    #   contexts/
    #   scripts/
    #   netscope.pem (synthetic)
    return tmp_path

@pytest.fixture
def tmp_context(tmp_tool_dir):
    """Ephemeral context inside tmp_tool_dir."""
    ctx_root = tmp_tool_dir / "contexts" / "testctx"
    (ctx_root / "config").mkdir(parents=True)
    (ctx_root / "cache").mkdir(parents=True)
    (ctx_root / "repositories").mkdir(parents=True)
    (ctx_root / "chromadb").mkdir(parents=True)
    (ctx_root / "config" / "context.ini").write_text(MINIMAL_CONTEXT_INI)
    return ctx_root

@pytest.fixture
def mock_subprocess(monkeypatch):
    """Patches subprocess.run to avoid real shell execution."""

@pytest.fixture
def mock_no_tools(monkeypatch):
    """Patches shutil.which to simulate clean environment (no git, python)."""

@pytest.fixture
def mock_playwright(monkeypatch):
    """Mocks Playwright browser context and page navigation."""
```

## Mocking Approach

- Heavy reliance on `unittest.mock.patch`.
- Module-level patches for heavy imports (e.g., Playwright in video-skill tests) so imports don't trigger browser installation.
- Synthetic data files in `tests/data/`.
- Real integrations gated by markers (`oauth`, `playwright`).

## Tiered Integration Tests

Three tiers in `tests/test_integration_skills.py` — run independently:

| Tier | Marker | Requires | What |
|------|--------|----------|------|
| 1 | `local` | (nothing) | Context, cache, RAG basics, skill interface checks |
| 2 | `oauth` | Valid OAuth token, network | API calls, env switching, token cache |
| 3 | `playwright` | Browser, SSO session | Log search, firewall |

CI runs only tier 1. Local-dev pre-merge runs tier 2. Manual runs hit tier 3.

---

## Per-Test Blueprints

Each entry describes purpose and key invariants. A developer should be able to regenerate the test from the description.

### test_auth_hardening.py
**Purpose**: `OAuthApiSkillBase` raises typed exceptions on auth failures instead of silently returning empty data.
**Tests**:
- `AuthenticationError` type and message.
- `ApiRequestError` carries url + method metadata.
- `_make_request` with no token → token acquisition called.
- 401 response → auto-refresh → retry once.
- Repeated 401 → raise `AuthenticationError`.
- 500 response → retry up to `retries`, exponential backoff.
- Per-environment token cache: tokens for `prod` and `dev` don't collide.
**Invariant**: the base class never returns silent empty; callers can trust either data or exception.
**Uses** a `FakeApiSkill(OAuthApiSkillBase)` inline subclass — no provider-specific code.

### test_cache_manager.py
**Purpose**: Repository cloning, retry logic, cert propagation.
**Tests**:
- `GIT_SSL_CAINFO`, `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE`, `CURL_CA_BUNDLE` are set in the subprocess env.
- Clone success / timeout retry / auth failure (no retry) / existing-repo skip.
- URL → repo-name extraction (HTTPS, SSH, bare).
**Generalized**: provider-agnostic.

### test_cert_propagation.py
**Purpose**: Corporate CA bundle reaches every subsystem (git, Playwright, pip, requests, curl).
**Tests**:
- `CacheManager` env vars.
- `PlaywrightSkillBase` cert path.
- Graceful handling when cert is missing.
- `install.py` env var setup.

### test_context_manager.py
**Purpose**: Context creation, isolation, configuration parsing.
**Tests**:
- Directory structure created correctly.
- Two contexts have separate caches; no cross-reads.
- `context.ini` parsing: issue-tracker project keys, log-search services.
**Generalized**: rename `jira` fixtures to `issues`; make the tests provider-agnostic.

### test_cross_platform.py
**Purpose**: OS detection and platform-specific behavior.
**Tests**:
- Platform detection (Darwin/Windows/Linux).
- Windows venv re-exec uses `subprocess.run`, not `os.execv`.
- Path handling (forward/backward slashes).
- UTF-8 encoding on Windows console.
- Microsoft Store Python rejection (regex check on path).
- Edge browser availability probe.
- `--break-system-packages` guarded on Windows only.

### test_dashboard_api.py
**Purpose**: Dashboard REST endpoints + HTML template generation.
**Tests**:
- `/api/health` returns `{"ok": true, "timestamp": ...}`.
- `/api/overview` returns JSON array of contexts.
- `index.html` exists and is substantial.
- Auth status probe reads browser profile existence.

### test_edge_preference.py
**Purpose**: Playwright launch prefers Edge on Windows; auth whitelist is populated.
**Tests**:
- `launch_browser_context` tries Edge channel first on Windows.
- Browser args include `--auth-server-whitelist=<configured hosts>`.
- Fallback chain: Edge → Chrome → Chromium.
- `msedge` install attempted before `chromium` install.
**Generalized**: the auth whitelist is pulled from config (`[server] auth_whitelist`); tests use a mock value.

### test_scm_walker.py (was test_gitlab_walker.py)
**Purpose**: Group-walker traversal.
**Tests**:
- `walk_group` requires a URL.
- URL normalization (trailing slashes, `http`→`https`, etc.).
- Result dataclass round-trips through `to_dict`.
- Results saved as `# Comment header\n<url>\n<url>\n`.

### test_graph_engine.py
**Purpose**: Graph builder, analyzer, differ, exporter, tree-sitter extractor.
**Tests**:
- Builder: node/edge creation; repo/class/api-endpoint nodes; contains/exposes edges; external deps; confidence tagging; save/load roundtrip; stats; empty context handling.
- Analyzer: `full_analysis` structure; god nodes (high degree); community detection; community ID stamping; empty/single-node cases.
- Diff: identical graphs → no changes; added/removed detection; markdown formatting.
- Exporter: JSON / HTML / report / GraphML; vis.js markers in HTML; markdown sections in report; empty-graph handling.
- Tree-sitter: `check()` platform/availability; languages list; nonexistent file; empty repo.
- Integration (skipped if no real context): build > 100 nodes/edges; find god nodes.
- Graph↔RAG bridge: boost empty/invalid results; preserve count; increase god-node scores; pass unmodified when no graph.
**Uses synthetic `ServiceA`/`ServiceB` fixtures — no real repos.**

### test_installer.py
**Purpose**: Bootstrap installer behavior.
**Tests**:
- git / Python detection.
- `.venv/` validation (existing, corrupted, missing).
- Cert env vars set.

### test_integration_auth.py  (marker: oauth)
**Purpose**: OAuth token acquisition, per-env caching, real API calls.
**Tests** (gated):
- Token acquisition per env (prod/staging/test/dev).
- Cached token reuse.
- Per-env tokens don't collide.
- Generic API skill: find/list/get via Core.
- Env switching updates URLs.
- Cache file format.

### test_integration_skills.py  (markers: local, oauth, playwright)
**Purpose**: Full skill suite integration tests, tiered.
**Tier 1 (local)**:
- Active context, directory structure, repositories present.
- Cache: global index, repo caches, API index.
- AI query tool: status / list / search.
- RAG: ChromaDB exists, has documents, search works.
- Skills: repository_query, log_search_url, mapping skill, voice_manager, claude_skills_manager.
- Post-install verification: Python version, tool script present, deps importable, Playwright installed, known contexts discoverable, active context set, repos cloned, caches built, RAG populated.
**Tier 2 (oauth)**: token acquisition, generic API calls, firewall skill, env switching.
**Tier 3 (playwright)**: log-search error-summary, firewall report.

### test_issue_cacher.py (was test_jira_cacher.py)
**Purpose**: Issue cache skill — config, caching, canonical status.
**Tests**:
- Default project key, custom project key, custom cache dir.
- `CachedIssue` dataclass fields.
- Canonical status logic: Done+Fixed → canonical; Cancelled → non_canonical; In-Progress → pending.
- Save + load roundtrip; load nonexistent returns `None`.

### test_known_contexts.py
**Purpose**: Structural validation of known-context bundles.
**Tests** (parametrized over all known contexts):
- Directory exists, ≥1 context, `CONTEXTS_OVERVIEW.md`, `README.md`.
- `definition.toml` parses; has `[context]` (name, display_name, description); `[repositories]`; inline entries look like git URLs with `.git` suffix; `[features]` booleans are booleans.
- `CLAUDE.md` exists; required sections (Overview, Repository Inventory, Architecture, Domain Terminology, Key Commands, Related Contexts); substantial length (>1000 chars); references `context use <name>`.
- Skills: YAML frontmatter with `---` delimiters; frontmatter has name + description; body > 100 chars.
- Knowledge: `index.json` parses; referenced files exist; JSON files parse.
- Cross-references: Related Contexts section references real contexts.
- `CONTEXTS_OVERVIEW.md` references all contexts; has Data Flow Map section; has Context Selection Guide.

### test_oauth_token.py
**Purpose**: Token skill cache mechanics.
**Tests**:
- Cache path location.
- Cached token with future `expires_at` is considered valid.
- Expired token detected.
- `get_oauth_token` convenience function exists and is callable.

### test_report_aggregation.py
**Purpose**: Report-generation code-name mapping and aggregation logic (the framework is provider-agnostic; adopters plug in their own entity schema).
**Tests**:
- Code→name resolution; handles case/whitespace; unknown → code; empty/None → "Unknown".
- Aggregation by platform × entity-type; filters non-success records.
- Aggregation by entity-category (arbitrary splits by a `type` field).
- Per-group aggregations: group by a configurable group-key field.
- Metrics aggregation: filter to year; sum success + retries; per-month breakdown.
**Test data**: use generic codes (e.g., `A`, `B`, `C`). The aggregation *logic* is domain-agnostic — adopters supply their own code vocabulary.

### test_setup_wizard.py
**Purpose**: Interactive wizard logic.
**Tests**:
- Import, init with base path.
- Context directory structure created correctly.
- `context.ini` creation with issue-tracker section.
- Non-interactive `--from-file` JSON schema validation.

### test_sync_manager.py
**Purpose**: Sync orchestration, status tracking, auto-RAG rebuild, freshness reporting.
**Tests**:
- `SyncConfig` defaults when section missing; custom values; empty CSV fields; partial config.
- `SyncStatusTracker`: empty status; mark/read persistence; multiple sources coexist; freshness (never/recent/failed); file created; corrupted file handling.
- `SyncManager`: default sync (repos only); explicit sources run all; source order; partial-failure → `overall="partial"`; auto-RAG when enabled; no auto-RAG when `--rag` explicit; freshness report; wiki skipped when no URLs.
- `WorkDir`: context dir created; shared dir; temp path/file (unique); cleanup.

### test_video_skill_guards.py
**Purpose**: Video skill path guards and dependency checks.
**Tests**:
- Rejects external paths (`/Users/...`, `~/Movies`); allows project-internal; `force_outside_project=True` bypasses.
- `_check_deps` returns dict with all keys (ffmpeg, ffprobe, ollama, whisper, pptx, Pillow, docx, sentence-transformers, numpy); missing deps have install hints; reports whisper backend + CPU count.

---

## New Tests to Add (rebuild)

When rebuilding as open-source, add:

- `test_providers_contract.py` — parametrized test that every registered provider adapter implements the required interface methods.
- `test_multi_provider_swap.py` — swap an issue-tracker provider at runtime; verify all downstream tests still pass.
- `test_auth_policy.py` — verify AuthenticationError is raised with actionable message + command, not a silent retry loop.
- `test_cache_policy.py` — verify authenticated data isn't persisted outside allowed paths.
- `test_sandbox_commands.py` — verify `server ps` / `server kill` work when bare `ps` / `kill` are denied.
- `test_installer_idempotent.py` — running `install.py` twice is safe and fast.

## Fixture Dependency Graph

```
conftest.py
├── tmp_tool_dir
│   └── (creates full expected layout under tmp_path)
├── tmp_context  ─── depends on tmp_tool_dir
│   └── (creates one context inside)
├── mock_subprocess
├── mock_no_tools
└── mock_playwright

Integration tests add:
├── oauth_skill ─ session-scoped, marker=oauth
├── api_skill_instance ─ session-scoped, marker=oauth
└── firewall_skill ─ session-scoped, marker=oauth
```

## Running the Tests

```bash
pytest                                   # default: -m "not oauth and not playwright"
pytest -m local                          # explicit local-only
pytest -m oauth                          # integration-auth (needs token)
pytest -m playwright                     # browser-required
pytest tests/test_graph_engine.py -v     # one file, verbose
pytest -k "community"                    # filter by name substring
```

## CI Recommendation

- Matrix: {Python 3.10, 3.11, 3.12, 3.13} × {macOS, Linux, Windows}.
- Default fast lane: `pytest -m "not oauth and not playwright and not slow"`.
- Nightly: add `-m slow` and tier-2 OAuth tests with secrets injected via env vars.
