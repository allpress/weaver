# Issue Tracker Provider

Supplies issues/tickets/work items. Reference adapter: JIRA.

## Interface

```python
@dataclass
class Issue:
    key: str                      # "PROJ-123"
    summary: str
    issue_type: str               # "Bug", "Story", "Task" — vocabulary is provider-configurable
    status: str
    resolution: Optional[str]
    priority: Optional[str]
    assignee: Optional[str]
    reporter: Optional[str]
    created: str                  # ISO-8601
    updated: str
    resolved: Optional[str]
    labels: list[str]
    components: list[str]
    epic_link: Optional[str]
    parent_key: Optional[str]
    story_points: Optional[float]
    linked_issues: list[dict]     # [{type, key, direction}]
    subtasks: list[str]
    comments: list[dict]          # [{author, created, body}]
    attachments: list[str]
    acceptance_criteria: Optional[str]
    custom_fields: dict[str, Any]

    # Classification for ML datasets — optional
    canonical_status: Literal["canonical", "non_canonical", "pending"]
    canonical_reason: Optional[str]


class IssueTracker(Provider):
    def search(self, query: str) -> Iterable[Issue]: ...       # JQL or provider-native
    def get(self, key: str) -> Issue: ...
    def my_issues(self, status_filter: str = "open") -> list[Issue]: ...
    def create(self, issue: Issue) -> str: ...                  # returns new key
    def comment(self, key: str, body: str) -> None: ...
    def attach(self, key: str, file_path: str, note: str = "") -> None: ...
    def analyze_defect(self, key: str) -> DefectAnalysis: ...   # optional deep-analysis capability
    def plan_story(self, key: str) -> StoryPlan: ...            # optional
    def ask(self, key: str, questions: list[str]) -> None: ...  # post clarifying questions
```

## Auth Models

The provider must declare one of:
- `"api_token"` — Basic Auth with email + token (Atlassian). **Preferred.** Works from sandbox, no browser needed.
- `"browser_sso"` — shared Playwright profile. Needed if the deployment only supports SSO.
- `"oauth"` — OAuth2 dance (Atlassian Cloud OAuth).

If both are available, prefer `api_token` (simpler, faster, sandbox-safe).

## Comment Formatting

Providers that accept rich text MUST convert plain markdown on input to the provider's format:
- JIRA Cloud → Atlassian Document Format (ADF) JSON.
- Linear → Markdown (native).
- GitHub Issues → Markdown.
- Azure DevOps → HTML.

The CLI accepts markdown uniformly; the adapter handles translation. **Never post raw markdown to a provider that requires ADF.**

## Bulk Cache

`scripts/skills/issue_cache_skill.py`:
- Wraps the issue-tracker provider.
- Fetches all issues matching a project/scope filter, writes `contexts/<name>/cache/issues/*.json` (one file per issue) + an index.
- Supports incremental updates via `updated > last_sync` filter.
- Supports canonical/non-canonical classification for ML dataset construction.
- Correlates with local git commits by scanning commit messages for issue keys.

## Cache Schema (on-disk)

```
contexts/<name>/cache/issues/
  index.json                # { last_sync, count, keys: [...] }
  PROJ-123.json             # full Issue serialization
  PROJ-124.json
  ...
```

`contexts/<name>/cache/issues/index.json`:
```json
{
  "last_sync": "2026-04-17T10:00:00Z",
  "provider": "jira",
  "project_keys": ["PROJ", "INFRA"],
  "count": 1250,
  "canonical_count": 420,
  "keys": ["PROJ-1", "PROJ-2", ...]
}
```

## Data Caching Policy

Issue cache files contain authenticated data. They are allowed on disk **only** if the user explicitly opts in via `issue-cache build` — and are scoped to one context. The default policy is still "fetch live, don't persist". Bulk cache is an opt-in feature for ML dataset building and offline search.

(The original deployment disabled this under stricter compliance. Open-source users can enable or disable based on their own data handling rules.)

## CLI Mapping

```
<tool> issues auth | check | me | get | analyze | plan | search | comment | attach | create | ask | wiki
<tool> issue-cache status | build | update | get | search | stats | export | cache-all <scope>
```

## Pluggability Checklist (for a new adapter)

To implement a new `IssueTracker` (e.g., Linear):

1. Create `scripts/api_skills/linear_api.py` subclassing the appropriate base.
2. Map Linear's GraphQL response to the `Issue` dataclass (unsupported fields → `None`).
3. Translate the search query (CLI uses JQL-like strings by default; Linear uses its own filter syntax — translate or pass through).
4. Declare `capabilities()` — Linear does not have Epics or subtasks in the JIRA sense; return the capability set honestly.
5. Handle the comment-format rewrite (Linear is markdown-native).
6. Add an entry in `_config/context_defaults.ini` under `[providers]` `issue_tracker = linear`.
7. Write an integration test in `tests/test_integration_issues.py`.

## Open-Source Reference Adapter Plan

Ship **two** adapters in the skeleton:
- `scripts/api_skills/jira_api.py` — covers Atlassian Cloud and Server.
- `scripts/api_skills/github_issues_api.py` — covers public GitHub.

These two cover ~80% of real-world use and demonstrate the two main interaction shapes (JIRA's rich custom-field model vs GitHub's flat/labels model). Other adapters are contributed as-needed.
