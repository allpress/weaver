# Minor Providers: ITSM, Cloud Logs, CI/CD

Briefer than the major providers — these are important but narrower in scope.

---

## ITSM (Service Tickets)

Reference adapter: ServiceNow.

### Interface

```python
@dataclass
class Ticket:
    id: str                      # "RITM12345", "INC67890"
    type: Literal["request", "incident", "change", "problem"]
    title: str
    description: str
    status: str
    assignee: Optional[str]
    requester: str
    created: str
    updated: str
    priority: Optional[str]
    url: str
    comments: list[dict]
    attachments: list[str]


class ITSM(Provider):
    def get(self, ticket_id: str) -> Ticket: ...
    def search(self, query: str) -> list[Ticket]: ...
    def comment(self, ticket_id: str, body: str) -> None: ...
```

### Auth

Typically SSO-only in enterprise deployments. Use the shared Playwright profile.

### Quirks

ServiceNow's classic UI is iframe-heavy; a browser adapter must know how to navigate the main frame vs embedded frames. Modern UIs (Now Experience) are cleaner. The adapter should detect which UI version is in use.

### CLI Mapping

```
<tool> itsm get <id> | search <query> | comment <id> <body>
```

### Alternative Adapters

- Jira Service Management — reuse the JIRA issue-tracker skill with a ticket-type filter.
- Zendesk, Freshservice — REST APIs, easy to implement.

---

## Cloud Logs

Reference adapter: AWS CloudWatch Logs.

### Interface

```python
class CloudLogs(Provider):
    def search(self, *, service: str, env: str, query: str,
               time_range: str = "1h", limit: int = 500) -> list[dict]: ...
    def tail(self, service: str, env: str, follow: bool = True) -> Iterable[dict]: ...
    def list_groups(self) -> list[str]: ...
    def stats(self, env: str) -> dict: ...                # volume stats
    def insights(self, query: str, time_range: str) -> list[dict]: ...  # CloudWatch Logs Insights
```

### Log Group Mapping

Like the log-search provider, cloud logs depend on a naming convention that varies per deployment. Store per-context:

```json
{
  "provider": "aws_cloudwatch",
  "log_groups": {
    "prod":    "/ecs/my-cluster-prod/{service}",
    "staging": "/ecs/my-cluster-staging/{service}",
    "dev":     "/ecs/my-cluster-dev/{service}"
  }
}
```

### Auth

- AWS: IAM role (preferred on EC2/ECS), `~/.aws/credentials`, `aws configure`, or env vars.
- GCP: service account JSON or `gcloud auth application-default login`.
- Azure: `az login` or service principal env vars.

### CLI Mapping

```
<tool> cloud-logs search <service> <env> [--search term --time 1h]
<tool> cloud-logs tail <service> <env>
<tool> cloud-logs groups
<tool> cloud-logs stats [env]
<tool> cloud-logs insights "<query>" [--time 1h]
```

### Alternative Adapters

GCP Cloud Logging, Azure Monitor Logs. Same shape, different SDKs (boto3 → google-cloud-logging → azure-monitor-query).

---

## CI/CD

No dedicated provider skeleton in the reference build — CI/CD data is usually read through the source-control adapter (GitLab pipelines are part of GitLab's API; GitHub Actions are part of GitHub's). Add a `ci_cd` subcapability on the `SourceControl` provider rather than a separate provider type.

### Minimum Capability (on SourceControl)

```python
def get_pipeline(self, project: str, pipeline_id: str) -> Pipeline: ...
def list_pipelines(self, project: str, status: Optional[str] = None) -> list[Pipeline]: ...
def get_pipeline_logs(self, project: str, pipeline_id: str) -> str: ...
```

### CLI Mapping

```
<tool> code pipelines <project> [--status failed]
<tool> code pipeline <project> <id>
<tool> code pipeline-logs <project> <id>
```

### When to split into its own provider

Split CI/CD into its own provider when the CI system is separate from source control (Jenkins separate from GitHub, CircleCI separate from GitLab). In that case, create a `CI` provider with the same three methods above and wire it independently.

---

## Summary Matrix

| Capability | SourceControl | IssueTracker | Wiki | LogSearch | ITSM | CloudLogs |
|------------|---------------|--------------|------|-----------|------|-----------|
| Auth | Token/SSO | Token/SSO | Token/SSO | Token/SSO (watcher) | SSO | Cloud IAM |
| Read | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Write | MR/PR | Issue CRUD | (rarely) | — | Comment | — |
| Bulk cache | (repo clones) | issue-cache | wiki-cache | — | — | — |
| RAG indexed | repo JSON | ✓ | ✓ | — (live) | — | — |
| Graph edges | contains/exposes/calls/depends_on | — | references | — | — | — |

The **graph** is primarily a source-control view. Issue tracker and wiki contribute cross-references that link into the graph. Log search and cloud logs are query-time only — they are too volatile and too voluminous to index structurally.
