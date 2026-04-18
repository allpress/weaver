# Pluggable Providers

The tool abstracts every external system as a **provider**: a small interface with at least an auth method, a fetch method, and a serialize method. The core of the system knows nothing about JIRA, GitLab, Splunk, or Confluence specifically — it only knows about the `IssueTracker`, `SourceControl`, `LogSearch`, and `Wiki` interfaces.

This is the single most important open-source design decision. Swapping providers is the primary extension point.

## Provider Families

| Family | Default adapter in reference build | Alternatives to support |
|--------|------------------------------------|-------------------------|
| Issue Tracker | JIRA (Cloud + Server) | GitHub Issues, Linear, Azure DevOps Work Items, Redmine |
| Source Control | GitLab (self-hosted + Cloud) | GitHub, Gitea, Bitbucket, Azure DevOps Repos |
| Log Search | Splunk Cloud | Elasticsearch/OpenSearch, Datadog Logs, New Relic Logs, Grafana Loki |
| Wiki | Confluence (Cloud + Server) | Notion, Obsidian vaults, Markdown folders, Sharepoint |
| ITSM | ServiceNow | Jira Service Management, Zendesk, Freshservice |
| Cloud Logs | AWS CloudWatch Logs | GCP Cloud Logging, Azure Monitor Logs |
| CI/CD | GitLab Pipelines | GitHub Actions, Jenkins, CircleCI, Azure Pipelines |
| Secrets/Auth | Browser SSO (Playwright-driven) | Vault, AWS Secrets Manager, Azure Key Vault, local keychain |
| Embedding backend | HuggingFace sentence-transformers | OpenAI, Cohere, local ONNX, locally-hosted LLM embedding |

## Provider Contract

Every provider is implemented as a **skill** (see `06-skills/skills-catalog.md`). The minimum interface:

```python
class Provider(ABC):
    name: str                       # "issue_tracker", "source_control", ...
    family: str                     # same as name or a subfamily

    # Auth
    def authenticate(self, **opts) -> AuthResult: ...
    def check_auth(self) -> AuthResult: ...

    # Capability probe (optional; some providers don't support everything)
    def capabilities(self) -> set[str]: ...

    # Fetch (read-only)
    def fetch(self, query: Query) -> Iterable[Record]: ...
    def get(self, id: str) -> Record: ...

    # Write (optional — may raise NotSupported)
    def create(self, record: Record) -> str: ...
    def update(self, id: str, patch: dict) -> None: ...

    # Serialization (Record is a dataclass; to_dict/from_dict)
```

The `execute(action, **kwargs)` pattern from the original skills maps onto this: `action` is the method name, `kwargs` are the arguments. The skill manager's `execute_skill(name, action=action, ...)` dispatches to the right provider instance.

## Auth Models

Three auth models are supported out of the box:

1. **Browser SSO (Playwright-driven)** — best when the organization uses corporate SSO and no API tokens are available. Uses a shared Chrome/Edge profile; one sign-in covers multiple providers. *Must run outside the AI-assistant sandbox.*
2. **API token (Basic Auth or Bearer)** — preferred when available. Atlassian API tokens, GitLab PATs, Splunk REST tokens.
3. **OAuth2 bearer** — for protected backend APIs. Tokens acquired via an AdminUI or MSAL endpoint, intercepted from browser traffic, cached per environment. Auto-refresh on 401.

Providers declare which models they support in `capabilities()`. The skill manager picks the strongest available.

## Auth Failure Policy (Critical)

If a provider call fails auth and no valid cached token is available:
- **Stop.** Do not retry, do not attempt background refresh from inside the AI-assistant sandbox.
- Return a typed `AuthenticationError` carrying the provider name and the command the user should run outside the sandbox to re-auth.
- The CLI formats this as a single-line actionable error: `Issue-tracker auth failed. Run: <tool> issues auth`.

This prevents the common failure mode where a script inside a sandbox tries to pop a browser, can't, and loops forever.

## Data Caching Policy (Critical)

**Must not** cache authenticated provider data on disk beyond the ephemeral browser profile:
- No issue-tracker JSON persisted after session end.
- No wiki pages persisted after session end.
- No log-search results persisted after session end.
- RAG/graph are rebuilt per session from live, authorized data.

**Exceptions** (allowed):
- `_config/playwright/.auth/` (short-lived browser cookies; gitignored; auto-expire).
- Video intelligence files produced from local video input.
- Repo JSON caches built from local git clones.
- Cross-repo indexes derived from repo JSON caches.

This policy is reflected in `.gitignore` and enforced at the cache-manager level.

## File Layout

Each provider lives in one of three places depending on how it integrates:

- `scripts/api_skills/<provider>_api.py` — REST/API providers (OAuth2 or API token).
- `scripts/playwright_skills/<provider>_browser.py` — browser-scrape providers (SSO-only sources).
- `scripts/skills/<provider>_cache_skill.py` — bulk-cache wrappers around either of the above, for ML-friendly local datasets.

The `scripts/api_skills/base.py` (`OAuthApiSkillBase`) and `scripts/playwright_skills/base.py` (`PlaywrightSkillBase`) provide the shared scaffolding (token cache, 401-auto-refresh, retries, SSL cert propagation, browser launch fallback chain).

## Per-Family Provider Pages

Detailed interfaces for each family live in this directory:

- `issue-tracker.md`
- `source-control.md`
- `log-search.md`
- `wiki.md`
- `itsm.md`
- `cloud-logs.md`
- `ci-cd.md`

## Related: Parsers

Providers fetch raw bytes; **parsers** turn them into `ContextNode`s. Parsers are a peer family with their own contract, safety rules, and a pinned canonical library per format (HTML, PDF, DOCX, Markdown, OpenAPI, source code, etc.). See [parsers.md](parsers.md).

Each page describes the interface, the default adapter's behavior, the caching/invalidation rules, and what must change to build an alternative adapter.
