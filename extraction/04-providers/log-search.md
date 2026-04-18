# Log Search Provider

Supplies application logs from a central log-search backend. Reference adapter: Splunk Cloud.

## Interface

```python
@dataclass
class LogEvent:
    timestamp: Optional[str]
    level: Literal["TRACE","DEBUG","INFO","WARN","ERROR","FATAL"]
    logger: str
    message: str
    app: str
    thread: Optional[str]
    pipeline: Optional[str]         # correlation-id-like field
    event_id: Optional[str]
    event_source: Optional[str]
    event_type: Optional[str]
    stack_trace: Optional[str]
    raw: str
    source: str
    sourcetype: str
    host: str
    extra: dict[str, Any]

    def matches(self, level=None, pattern=None, logger_pattern=None) -> bool: ...


@dataclass
class LogSearchResult:
    success: bool
    service: str
    environment: str
    time_range: str
    events: list[LogEvent]
    total_count: int
    filtered_count: int
    url: str                        # deep-link to provider UI
    query: str
    execution_time_ms: int
    error: Optional[str]


class LogSearch(Provider):
    def authenticate(self) -> AuthResult: ...
    def search(self, *, service: str, env: str, search: Optional[str] = None,
               level: Optional[str] = None, time_range: str = "1h",
               limit: int = 500) -> LogSearchResult: ...
    def errors(self, service: str, env: str, time_range: str = "1h") -> LogSearchResult: ...
    def analyze(self, service: str, env: str, time_range: str = "1h") -> AnalysisReport: ...
    def correlate(self, services: list[str], env: str, key: str = "pipeline") -> CorrelationReport: ...
    def trace(self, trace_id: str, services: list[str], env: str) -> TraceReport: ...
    def list_indexes(self) -> list[str]: ...
```

## Auth Models

- `"bearer_token"` — Splunk REST API token. **Preferred** when available.
- `"browser_sso"` — fallback via shared Playwright profile. Required when the tenant has no REST token support (common in some Splunk Cloud deployments).

**Watcher dispatch** (important): browser-based log searches MUST run through the watcher pattern (see `05-modules/cdp-watcher.md`), not directly in the CLI process. Directly instantiating a Playwright browser per query is what historically caused CDP lockups and session exhaustion. The pattern is:

```
CLI process                Watcher process
    │                           │
    │  dispatch("logs search",  │
    │    service, env, ...)     │
    ├──────────────────────────▶│
    │                           │ execute in browser
    │                           │ write result JSON
    │  read result file         │
    │◀──────────────────────────┤
```

## Service-to-Index Mapping

Real deployments have a *lot* of Splunk indexes, and log volume forces discipline: you must know which index to query for which service, or queries time out or return the wrong data.

The reference build stores this mapping as JSON under `_config/log_search/<service>.json`:

```json
{
  "service": "service-a",
  "indexes": {
    "prod":    ["app-prod-service-a", "infra-prod-service-a"],
    "staging": ["app-staging-service-a"],
    "dev":     ["app-dev-service-a"]
  },
  "fields": {
    "correlation_id": "traceId",
    "service_name":   "app",
    "log_level":      "level"
  },
  "example_queries": [
    { "name": "errors_last_hour",
      "query": "index=app-prod-service-a level=ERROR earliest=-1h" },
    { "name": "trace_lookup",
      "query": "index=app-prod-service-a traceId={trace_id}" }
  ],
  "traversal": {
    "upstream":   { "index": "app-prod-gateway",  "key": "traceId" },
    "downstream": { "index": "app-prod-worker",   "key": "traceId" }
  }
}
```

The `traversal` section defines how a lifecycle trace jumps between services: which index holds upstream logs, which holds downstream, which field is the join key. Each deployment configures its own traversal topology per service — no hardcoded system names.

## Cross-System Trace

`trace <trace_id> <services> <env>` walks the service topology defined in the per-context mapping:

1. Start at the primary service's index.
2. Find the event with matching `trace_id`.
3. For each configured upstream/downstream hop, run a parallel query in that service's index using the join key from the found event.
4. Assemble a chronological multi-service trace.

This is a killer feature. The investigation "where did this event go?" crosses many logs; one command collapses it.

## Index Discovery

`list_indexes` is an introspection command: hit the provider's introspection API (Splunk `rest /services/data/indexes`, Elastic `_cat/indices`, etc.) and list accessible indexes. Useful when configuring a new service mapping — the user can see which indexes actually exist.

## Playbook

`logs playbook [topic]` ships as a static help-content command that explains how to investigate common issues in this log backend. Topics:

- `overview` — quick orientation
- `indexes` — how indexes are organized
- `sources` — how log sources map to services
- `queries` — common query patterns + syntax
- `auth` — how to auth (watcher pattern)
- `investigation` — step-by-step investigation playbook
- `pitfalls` — common mistakes
- `reference` — field reference

Content lives in `docs/log-search-playbook.md` and is rendered inline when requested.

## CLI Mapping

```
<tool> logs auth | check | search | errors | analyze | correlate | trace | report
<tool> logs indexes | upstream | downstream | lifecycle    # traversal (generalized)
<tool> logs playbook [topic]
```

## Pluggability Checklist

New adapter (e.g., Elasticsearch/OpenSearch):

1. `scripts/api_skills/elastic_logs.py` implementing `LogSearch`.
2. Translate search to the provider's query DSL (Splunk SPL → Lucene/ES-DSL).
3. Map `LogEvent` from the provider's response shape.
4. Implement `list_indexes` via `_cat/indices`.
5. Per-context mapping files use provider-specific index names.
6. `[providers] log_search = elastic` in context config.

## Open-Source Reference Adapters

Ship two:
- `scripts/api_skills/splunk_logs.py` — Splunk Cloud + Enterprise (REST token + browser fallback).
- `scripts/api_skills/elastic_logs.py` — OpenSearch / Elasticsearch.

Datadog, Loki, New Relic are contributable.
