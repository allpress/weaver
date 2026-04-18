# Skills Catalog

Skills are the extension primitive. A skill is a self-contained capability with a consistent `execute(action, **kwargs)` interface. Adding a new capability = writing a new skill.

Three families:
1. **Domain skills** (`scripts/skills/`) — cache/transformation/analysis of specific data types.
2. **API skills** (`scripts/api_skills/`) — REST/OAuth2 adapters for backend services.
3. **Playwright skills** (`scripts/playwright_skills/`) — browser-automation adapters for SSO-only sources.

---

## Skill Base Interface

```python
class BaseSkill(ABC):
    def __init__(self, name: str, description: str): ...

    @abstractmethod
    def get_available_actions(self) -> list[dict[str, str]]: ...
        # Returns [{name, description, args, ...}]

    @abstractmethod
    def execute(self, action: str, **kwargs) -> dict[str, Any]: ...
        # Returns {success: bool, data?: any, error?: str, ...}

    def get_info(self) -> dict[str, str]:
        return {"name": self.name, "description": self.description}
```

Feature-flag pattern (every skill):

```python
try:
    from skills.<skill_name> import SkillClass
    <SKILL>_AVAILABLE = True
except ImportError:
    <SKILL>_AVAILABLE = False
    SkillClass = None
```

This lets the tool start even if optional dependencies aren't installed. Individual skills surface their missing-dep error only when invoked.

## Skill Manager

**Location**: `scripts/skill_manager.py`

```python
class SkillManager:
    def __init__(self): ...
    def register(self, skill: BaseSkill) -> None: ...
    def list_skills(self) -> list[dict]: ...
    def execute_skill(self, name: str, action: str, **kwargs) -> dict: ...
```

Dispatch: `<tool> skill <skill_name> <action> [--arg value]` → `SkillManager.execute_skill(name, action, **parsed_kwargs)`.

---

## Part 1 — Domain Skills

Each lives in `scripts/skills/<skill>.py`.

### issue_cache_skill

**Purpose**: Bulk cache of issues for ML training, offline search, commit correlation.

**Interface**:
```python
class IssueCacheSkill(BaseSkill):
    actions = ["cache", "status", "get", "search", "export", "rebuild", "cache_all"]

@dataclass
class CachedIssue:
    # See 04-providers/issue-tracker.md for full shape
    canonical_status: Literal["canonical", "non_canonical", "pending"]
    canonical_reason: Optional[str]
```

**Canonical status** = ML-usable (Done + Fixed), non_canonical (Cancelled/Won't Fix), or pending. Enables filtered ML dataset export.

**Dependencies**: issue-tracker provider (via `skill_manager`), local cache dir, optional git scanning for commit correlation.

**Pluggability**: swap provider independently; canonical rules live in a small provider-specific config dict.

### wiki_cache_skill

**Purpose**: Crawl and cache wiki pages for RAG ingestion.

**Interface**:
```python
class WikiCacheSkill(BaseSkill):
    actions = ["crawl", "status", "get", "search", "export"]

@dataclass
class CachedPage:
    # See 04-providers/wiki.md for full shape
    sections: list[dict]       # heading-boundary chunks
    breadcrumb: list[str]
    def to_rag_chunks(chunk_size=1500, overlap=200) -> list[dict]: ...
```

**Notable**: heading-aware chunking respects section boundaries before splitting by word count. Each chunk retains breadcrumb for context.

### llm_skill

**Purpose**: Unified local LLM inference. Auto-detect best backend.

**Interface**:
```python
class LLMSkill(BaseSkill):
    actions = ["check", "chat", "complete", "list_models"]

class LocalLLM:
    def __init__(self, model: str = "auto"): ...
    def chat(self, system_prompt: str, user_msg: str) -> str: ...
    def complete(self, prompt: str, max_tokens: int = 512) -> str: ...
```

**Backends (priority)**:
1. **MLX-LM** (Apple Silicon, Metal GPU) — fastest.
2. **Ollama** (CPU/GPU, cross-platform) — universal fallback.
3. (Plugin) Remote — OpenAI/Anthropic/local OpenAI-compatible server.

**Sandbox safety**: HuggingFace cache redirected to project-local (`HF_HOME=.hf_cache`) to avoid sandbox deny-read on `~/.cache/huggingface`.

### transcribe_skill

**Purpose**: Audio transcription (Whisper).

**Interface**:
```python
class LocalTranscriber(BaseSkill):
    def __init__(self, model_size: str = "base"): ...
    actions = ["check", "transcribe", "list_models"]
    def transcribe(self, audio_path: str) -> list[TranscriptSegment]: ...

@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str
    source_video: str = ""
    source_video_index: int = 0
    confidence: float = 0.0
```

**Backends**:
1. **mlx-whisper** (Apple Silicon) — 5–10x faster.
2. **faster-whisper** (CPU) — universal fallback.

**Sandbox safety**: MLX availability probed via subprocess (NSException can crash the parent if tested in-process on sandboxed builds).

### video_to_doc_skill

**Purpose**: Convert video (or folder of videos) to PPTX/DOCX with transcription, key frames, and cross-video deduplication.

**Interface**:
```python
class VideoToDocSkill(BaseSkill):
    actions = ["convert", "check", "list", "status"]

@dataclass
class KeyFrame:
    timestamp: float
    frame_number: int
    description: str
    thumbnail_path: str

@dataclass
class AnalyzedChunk:
    start_time: float
    end_time: float
    transcript: str
    slide_title: str
    slide_content: list[str]
    key_frame: Optional[KeyFrame]
    source_video: str

class VideoExtractor:
    def extract_audio(self, video_path: str) -> bytes: ...
    def extract_frames(self, video_path: str) -> list[KeyFrame]: ...
    def extract_metadata(self, video_path: str) -> dict: ...
```

**Merge modes** (for folder input): `chapters` (one chapter per video) or `unified` (cross-video narrative).

**Deduplication**: sentence-transformer embeddings across videos, cosine similarity threshold, drop near-duplicates.

**Dependencies (lazy-loaded)**: ffmpeg, transcribe_skill, llm_skill, python-pptx, python-docx, Pillow, sentence-transformers.

**Path guard**: source must be inside project directory unless `--force-outside-project`. Prevents sandbox escape for temp files.

### video_intel_skill

**Purpose**: Extract structured intelligence from videos (facts, decisions, action items, people, systems, questions) via LLM prompt. Output is markdown auto-picked-up by RAG indexer.

**Interface**:
```python
class VideoIntelSkill(BaseSkill):
    actions = ["parse", "list", "status", "check"]
```

**Prompt** (approximately):
```
Extract structured knowledge from this transcript chunk. Return JSON with:
{
  "source_type": "training|meeting|presentation|demo|discussion",
  "topic": "short topic name",
  "key_facts": [...],
  "decisions": [...],
  "action_items": [...],
  "people": [{"name": "...", "role": "..."}],
  "systems": [...],
  "dates": [{"date": "...", "context": "..."}],
  "questions": [{"question": "...", "answered": true|false, "answer": "..."}],
  "summary": "2-3 sentence summary"
}
```

**Manifest**: `video_intelligence_manifest.json` — dedupe by SHA-256(first 64KB) + size + mtime.

### firewall_skill

**Purpose** (generalized): egress/firewall analysis — determine whether outbound traffic from a given service to a given destination is allowed. Parses firewall logs / policy config.

**Interface**:
```python
class FirewallSkill:
    actions = ["check", "resolve", "report"]
```

**Pluggability**: vendor-specific (Palo Alto / Fortinet / Cisco / Check Point). Ship with a vendor-abstraction layer that accepts log format via config.

### cloud_logs_skill (was cloudwatch)

**Purpose**: Query cloud-provider log store (CloudWatch / Cloud Logging / Azure Monitor).

**Interface**: see `04-providers/itsm-and-cloud-logs-and-ci.md`.

### pptx_fill_skill

**Purpose**: Generate branded PPTX from structured JSON.

**Slide types**:
- `title` — cover
- `section` — section divider
- `bullets` — standard bullets
- `two_column` / `three_column`
- `table`
- `stat_callout` — big number
- `image_text`
- `quote`
- `closing`

**Pluggability**: swap corporate template + color palette per deployment. Brand constants live in a dataclass you override.

### mapping_skill (extension point)

A **mapping skill framework** for source-to-target data-model translation. Each mapping bundle is data, not code:

```python
class MappingSkill(BaseSkill):
    actions = ["overview", "src_field", "dst_field", "enum", "gaps", "patterns", "section"]

    def __init__(self, mapping_name: str, base_path: Path): ...
    # Loads:
    #   mappings/<name>/source_fields.json
    #   mappings/<name>/target_fields.json
    #   mappings/<name>/enums.json
    #   mappings/<name>/gaps.json
    #   mappings/<name>/patterns.json
    #   mappings/<name>/sections.json
```

Adopters produce mapping bundles for their own source/target models. No code changes required to ship a new mapping.

### domain_knowledge_skill

**Purpose**: Supply AI-accessible tips/patterns/gotchas for specific domain entities.

**Layout**:
```
_config/knowledge/                            # global fallback
_config/known_contexts/<ctx>/knowledge/       # context-specific (preferred)
  index.json                                  # {data_type: file, ...}
  <entity>.json                               # adopter-defined
```

**Resolution**: explicit-context → active-context → global fallback.

---

## Part 2 — API Skills

**Location**: `scripts/api_skills/`

### Base: OAuthApiSkillBase

```python
class OAuthApiSkillBase(ABC):
    def __init__(self, skill_name: str, description: str,
                 base_path: Optional[Path] = None): ...

    def _get_token(self, force_refresh: bool = False,
                   adminui_url: str = "") -> str: ...
        # Token cache keyed by adminui_url (environment-specific)
        # TTL ~ 3500s (refresh before 1h expiry)
        # On 401 from caller, force_refresh=True and retry once

    def _make_request(self, url: str, method: str = "GET",
                      params: dict = None, json_data: dict = None,
                      headers: dict = None, retries: int = 3,
                      retry_on_500: bool = True,
                      timeout: int = 60) -> requests.Response: ...
        # Raises AuthenticationError on unrecoverable auth failure
        # Raises ApiRequestError on HTTP error after retries

    def _save_result(self, filename: str, data: Any) -> Path: ...
    def _load_result(self, filename: str) -> Optional[Any]: ...

    @abstractmethod
    def get_available_actions(self) -> list[dict]: ...
    @abstractmethod
    def execute(self, action: str, **kwargs) -> dict: ...


class AuthenticationError(Exception): ...
class ApiRequestError(Exception):
    url: str; method: str
```

### Example Adapter (Template)

`scripts/api_skills/template_entity_api.py` — ship as the starter for anyone building a new OAuth2-protected API adapter.

```python
class TemplateEntityApiSkill(OAuthApiSkillBase):
    SERVICE_URLS = {
        "prod":    "https://api.example.com",
        "staging": "https://staging.api.example.com",
        "test":    "https://test.api.example.com",
        "dev":     "https://dev.api.example.com",
    }
    ADMINUI_URLS = { ... }                     # used to scrape token via Playwright

    def execute(self, action: str, **kwargs) -> dict:
        if action == "get_entity":
            return self._get_entity(**kwargs)
        elif action == "list_entities":
            return self._list_entities(**kwargs)
        # ...
```

Environment persistence: write selected env to `.api_env` file in project root so subsequent commands inherit. Override with `--env`.

### access_control_skill

**Purpose**: Authority resolution across a fleet of services. Map IdP groups to permissions/endpoints.

**Input**: per-service config (YAML/JSON) with authority declarations + IdP group mappings.
**Output**: who-can-do-what reports, 403 diagnostics, cross-environment diffs.

**Pluggability**: swap IdP (AD / Okta / Azure Entra ID / Keycloak) via `identity_provider.py` interface.

### domain_knowledge (API facet)

A thin wrapper over file-based knowledge (see domain skills above) presented as a skill so it can be invoked via `<tool> skill domain_knowledge get_tips --data_type=<adopter-defined-type>`.

---

## Part 3 — Playwright Skills

**Location**: `scripts/playwright_skills/`

### Base: PlaywrightSkillBase

```python
class PlaywrightSkillBase(ABC):
    def __init__(self, skill_name: str, description: str,
                 base_path: Optional[Path] = None): ...

    def launch_browser_context(self, playwright, headless=True,
                               viewport=None) -> BrowserContext:
        # Try CDP server first → direct launch (Chrome → Edge → Chromium)

    def _get_chrome_user_data_dir(self) -> Path: ...
        # Shared profile: _config/playwright/chrome-profile

    def _get_proxy_cert_path(self) -> Optional[str]: ...

    def get_auth_state_path(self, auth_name: str) -> Path: ...
    def has_auth_state(self, auth_name: str) -> bool: ...

    def save_screenshot(self, page, name: str) -> str: ...
    def save_result(self, result: PlaywrightTaskResult) -> str: ...

    def retry_operation(self, func, max_retries=3, delay=2.0, **kwargs): ...

    @abstractmethod
    def execute(self, action: str, **kwargs) -> dict: ...


@dataclass
class PlaywrightTaskResult:
    success: bool
    task_name: str
    data: Optional[Any]
    error: Optional[str]
    screenshots: list[str]
    execution_time_ms: int
    timestamp: str
```

### Launch Chain

```
1. CDP server running on localhost? → connect (fastest, preserves SSO)
2. Else: persistent context with shared profile (tries Chrome → Edge → Chromium)
3. Else: fresh non-persistent context
```

Platform preference: Windows prefers Edge (Windows Integrated Auth, corporate policy); macOS prefers Chrome.

### oauth_token_skill

**Purpose**: acquire OAuth2 bearer token by intercepting the Authorization header from a browser session that's already logged in to the AdminUI / MSAL endpoint.

**Interface**:
```python
class OAuthTokenSkill(PlaywrightSkillBase):
    actions = ["get_token", "check_token", "clear_token"]
```

**Strategy** (two paths):
1. Intercept the token-endpoint response (fresh auth).
2. Intercept outgoing Authorization headers (cached SSO).

**Cache**: `_config/playwright/.auth/oauth_tokens.json`, keyed by `client_id@hostname@env`.

### issue_tracker_browser (was jira_browser)

**Purpose**: fallback when only browser SSO works. Scrape issue details from the issue tracker's web UI.

Replaced by REST API (see `04-providers/issue-tracker.md`) whenever possible — this skill is the backup path.

### scm_browser (was gitlab_browser)

Same: fallback path. Uses the shared Playwright profile.

### log_search_browser (was splunk_browser)

Critical path for Splunk Cloud tenants that don't expose REST tokens. See `04-providers/log-search.md`.

### itsm_browser (was servicenow_browser)

For ITSM systems requiring SSO. Handles iframe navigation.

### Support Skills

- **browser_cdp.py** — CDP connection manager.
- **header_analyzer.py** — intercept HTTP headers, verify required headers are being sent.
- **network_capture.py** — record network activity to HAR file.
- **extract_diagrams.py** — render embedded diagrams from wiki pages.

---

## Claude Skills Manager

**Location**: `scripts/claude_skills_manager.py`

Copies per-context Claude Code slash-command skills from `_config/known_contexts/<ctx>/skills/` into `~/.claude/skills/<ctx>/` so they're invokable as `/<ctx>-<skill>` in any Claude Code session.

```python
class ClaudeSkillsManager:
    def discover_skills(self, context_name: str) -> list[dict]: ...
    def install_context_skills(self, context_name: str) -> list[str]: ...
    def sync_all(self) -> list[str]: ...
    def list_installed(self) -> list[dict]: ...
```

---

## Adding a New Skill

1. Create `scripts/<family>/<skill>.py`.
2. Subclass `BaseSkill` (or `OAuthApiSkillBase` / `PlaywrightSkillBase`).
3. Implement `get_available_actions` and `execute`.
4. Register in `skill_manager.py` via the feature-flag import pattern.
5. Add CLI dispatch in `<tool>.py` if the skill deserves a top-level command (most do — `<tool> <skill-name> <action>`).
6. Write a test in `tests/test_<skill>.py`.
7. Document in `_config/knowledge/skills/<skill>.md` so the dashboard and AI assistants can discover it.

## Skill Summary Matrix

| Family | Base | Key Use |
|--------|------|---------|
| Domain | `BaseSkill` | Cache, transform, analyze data |
| API | `OAuthApiSkillBase` | REST/OAuth2 backends |
| Playwright | `PlaywrightSkillBase` | Browser-SSO-only sources |

| Skill | Family | Dependencies | Essential? |
|-------|--------|--------------|------------|
| issue_cache | Domain | issue provider | No (opt-in) |
| wiki_cache | Domain | wiki provider | No (opt-in) |
| llm | Domain | MLX or Ollama | No (for local LLM features) |
| transcribe | Domain | Whisper | No (for video) |
| video_to_doc | Domain | ffmpeg, LLM, Whisper | No |
| video_intel | Domain | transcribe, LLM | No |
| firewall | Domain | log or policy source | No |
| cloud_logs | Domain | cloud SDK | No |
| pptx_fill | Domain | python-pptx | No |
| mapping | Domain | mapping bundle files | No |
| domain_knowledge | Domain | knowledge files | Yes (default) |
| access_control | API | auth configs | No |
| oauth_token | Playwright | Playwright | Yes if using OAuth APIs |
| scm_browser | Playwright | Playwright | No (REST preferred) |
| issue_browser | Playwright | Playwright | No (REST preferred) |
| log_search_browser | Playwright | Playwright | Yes for Splunk Cloud |
| itsm_browser | Playwright | Playwright | No (optional) |

**Essential = needed for the minimum viable build**. Everything else is add-on.
