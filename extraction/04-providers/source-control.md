# Source Control Provider

Supplies repositories, files, groups/orgs, and PRs/MRs. Reference adapter: GitLab.

## Interface

```python
@dataclass
class Repo:
    id: str
    name: str
    path: str
    full_path: str
    description: str
    web_url: str
    ssh_url: str
    http_url: str
    default_branch: str
    visibility: Literal["private", "internal", "public"]
    last_activity: Optional[str]
    namespace: str
    topics: list[str]


@dataclass
class RepoFile:
    name: str
    path: str
    type: Literal["blob", "tree"]
    size: int
    content: Optional[str]    # populated only for blobs when fetched


@dataclass
class MergeRequest:
    id: str
    iid: int
    project: str
    source_branch: str
    target_branch: str
    title: str
    description: str
    state: Literal["opened", "merged", "closed"]
    author: str
    approvals: list[dict]
    pipelines: list[dict]
    threads: list[dict]
    web_url: str


class SourceControl(Provider):
    def search_projects(self, query: str, visible: bool = True) -> list[Repo]: ...
    def list_projects(self, group: Optional[str] = None) -> list[Repo]: ...
    def list_groups(self, search: Optional[str] = None) -> list[dict]: ...
    def project(self, path: str) -> Repo: ...
    def browse(self, project: str, dir_path: str = "/") -> list[RepoFile]: ...
    def get_file(self, project: str, file_path: str, ref: str = "HEAD") -> RepoFile: ...
    def clone(self, project: str, dest: str, branch: Optional[str] = None) -> None: ...
    def walk_group(self, group_url: str) -> list[Repo]: ...
    def token(self) -> str: ...                                    # PAT management
    def create_mr(self, project: str, **opts) -> MergeRequest: ...
    def read_mr(self, url_or_iid, show_resolved: bool = False) -> MergeRequest: ...
```

## Auth Models

- `"api_token"` — personal access token (GitLab PAT, GitHub PAT). **Preferred.**
- `"browser_sso"` — shared Playwright profile for orgs requiring SSO for API access.
- `"ssh"` — for clone-only workflows, use existing SSH keys.

Authentication is often shared across providers when the org uses one SSO: the same Playwright profile authenticates the source-control adapter, issue-tracker adapter, wiki adapter, and log-search adapter simultaneously. This is an intentional feature, not a bug.

## Group Walker

The **group walker** is a signature feature: given a group/org URL, recursively enumerate every project (including nested subgroups). Used in the setup wizard to bootstrap a context from a single URL.

```python
def walk_group(group_url: str) -> list[Repo]:
    # 1. Parse URL → (group_path, provider_instance)
    # 2. API-list projects in group (paginated)
    # 3. Recurse into subgroups
    # 4. Deduplicate by project id
    # 5. Return flat list
```

Performance note: for large orgs (1000+ repos), paginate and stream — don't load all at once.

## Git Integration

Cloning goes through `scripts/cache_manager.py`:
- Uses `git` CLI via subprocess.
- Propagates corporate CA cert (see `03-install-setup/` for the env-var contract).
- Credential helper: file-based via `.git-credentials`, never the OS keychain (keychain isn't accessible from sandboxed AI harnesses; file-based works universally).
- Retries transient failures (3 attempts, exponential backoff). Does **not** retry auth failures.
- Supports `url,branch` override syntax in repo-list files to pin branches.

## Repository Config Format

`contexts/<name>/config/repositories/<list>.txt`:
```
# Comments ignored
https://gitlab.example.com/group/repo-a.git
https://gitlab.example.com/group/repo-b.git,main
git@github.com:org/repo-c.git,develop
```

One URL per line. Optional `,branch` override. Comments with `#`.

## Push/MR Creation

`create_mr` wraps the provider's MR/PR API. MR description format should follow a consistent convention (project code, issue key, "Closes" directive for automatic issue closure on merge).

The original implementation used a custom `/merge-request` slash command (Claude Code skill) that formats MRs per org convention. Ship this as a template in `_config/known_contexts/<name>/skills/merge-request/`.

## CLI Mapping

```
<tool> code auth | check | search | list | groups | project | browse | get | clone | walk | token | mr | mr-read
```

## MR Read (review automation)

`mr-read` fetches a merge request's metadata, approvals, pipelines, and unresolved review threads via REST (no browser). Useful for:
- Claude Code answering "what's blocking this MR?"
- Babysitting PR reviews via the `/loop` skill.
- Building a per-context "my open MRs" dashboard.

## Pluggability Checklist

For a new adapter (e.g., GitHub):

1. `scripts/api_skills/github_scm.py` implementing `SourceControl`.
2. Translate `walk_group` to walk GitHub orgs + repos.
3. Translate GitLab MR vocabulary to GitHub PR vocabulary (MR↔PR, approvals, checks/pipelines, review threads).
4. Implement token management (GitHub CLI or manual PAT).
5. Context config: `[providers] source_control = github`.
6. Integration test with a public repo.

## Open-Source Reference Adapters

Ship two:
- `scripts/api_skills/gitlab_scm.py` — self-hosted + GitLab Cloud.
- `scripts/api_skills/github_scm.py` — github.com + GHES.

Bitbucket/Gitea are contributable as needed.
