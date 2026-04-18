# Data Models & Cache Schemas

Every persistable artifact is a JSON or markdown file on disk. Rebuild these shapes exactly and the rest of the system reads them without modification.

## Cache Tree (Per Context)

```
contexts/<name>/cache/
├── indexes/
│   ├── global_index.json             # master cross-repo index
│   ├── apis.json                     # all API endpoints
│   ├── source_map.json               # source-file map
│   └── repos_quick_ref.json          # quick ref for dashboards
├── repos/
│   └── <repo_name>.json              # per-repo structured cache
├── issues/
│   ├── index.json                    # {last_sync, count, keys}
│   └── <KEY>.json                    # one file per issue
├── wiki/
│   ├── index.json
│   └── <page_id>.json
├── architecture/
│   └── *.md                          # manual architecture docs
├── video_intelligence/
│   ├── manifest.json
│   └── <slug>/
│       └── chunk_<n>.md              # LLM-extracted intelligence
├── graph/
│   ├── graph.json                    # current knowledge graph
│   ├── GRAPH_REPORT.md               # analyzer output
│   └── snapshots/
│       └── <ISO>.json                # for diff
├── api_results/
│   └── <skill>/                      # adapter result cache (opt-in)
├── firewall/
│   └── <env>/
└── sync_status.json                  # freshness tracker
```

---

## Repo Cache (`cache/repos/<name>.json`)

```json
{
  "name": "service-a",
  "path": "/path/to/contexts/<ctx>/repositories/service-a",
  "indexed_at": "2026-04-17T10:30:00Z",
  "summary": {
    "total_files": 450,
    "source_files": 200,
    "controllers": 12,
    "services": 35,
    "repositories": 20,
    "models": 40,
    "tests": 80
  },
  "structure": {
    "dirs": {
      "src": {
        "dirs": { "main": { ... }, "test": { ... } },
        "files": ["pom.xml"]
      }
    },
    "files": ["README.md", ".gitignore"]
  },
  "source_files": [
    {
      "path": "src/main/java/com/example/api/UserController.java",
      "package": "com.example.api",
      "class": "UserController",
      "lines": 145,
      "hash": "abc123def",
      "extension": ".java"
    }
  ],
  "apis": [
    { "method": "GET",  "path": "/api/users/{id}", "file": "src/.../UserController.java" },
    { "method": "POST", "path": "/api/users",      "file": "src/.../UserController.java" }
  ],
  "services":    [ { "name": "UserService",      "path": "src/.../UserService.java" } ],
  "repositories":[ { "name": "UserRepository",   "path": "src/.../UserRepository.java" } ],
  "models":      [ { "name": "User",             "path": "src/.../User.java" } ],
  "dependencies": [
    { "type": "implementation", "artifact": "org.springframework:spring-web:6.0.0" }
  ],
  "build": {
    "type": "maven",
    "version": "3.8.1",
    "file": "pom.xml"
  },
  "readme": "# Service A\n..."
}
```

## Global Index (`cache/indexes/global_index.json`)

```json
{
  "generated_at": "2026-04-17T10:30:00Z",
  "context": "<name>",
  "repos": [
    { "name": "service-a", "path": "...", "files": 450, "apis": 12 }
  ],
  "totals": {
    "repos": 10,
    "files": 4500,
    "source_files": 2000,
    "apis": 120,
    "services": 350
  }
}
```

## APIs Index (`cache/indexes/apis.json`)

```json
{
  "total": 245,
  "by_repo": {
    "service-a": [
      {
        "method": "GET",
        "path": "/api/users/{id}",
        "repo": "service-a",
        "controller": "com.example.api.UserController",
        "file": "src/.../UserController.java"
      }
    ],
    "service-b": [...]
  }
}
```

## Source Map (`cache/indexes/source_map.json`)

```json
{
  "total_files": 1200,
  "by_repo": {
    "service-a": {
      "source_count": 450,
      "test_count": 80,
      "by_package": {
        "com.example.api": { "classes": 12, "files": 12 },
        "com.example.service": { "classes": 35, "files": 35 }
      }
    }
  }
}
```

## Sync Status (`cache/sync_status.json`)

```json
{
  "repos":  { "last_sync": "2026-04-17T10:00:00Z", "last_result": "success", "duration_seconds": 45.2, "repos_updated": 12, "repos_failed": 0 },
  "issues": { "last_sync": "2026-04-17T10:05:00Z", "last_result": "success", "issues_updated": 250 },
  "wiki":   { "last_sync": "never" },
  "rag":    { "last_sync": "2026-04-17T10:10:00Z", "last_result": "success", "documents_added": 320 }
}
```

---

## Issue Cache (`cache/issues/<KEY>.json`)

```json
{
  "key": "PROJ-123",
  "summary": "...",
  "description": "...",
  "issue_type": "Bug",
  "status": "In Progress",
  "resolution": null,
  "priority": "High",
  "assignee": "alice@example.com",
  "reporter": "bob@example.com",
  "created": "2026-03-01T10:00:00Z",
  "updated": "2026-04-17T08:30:00Z",
  "resolved": null,
  "labels": ["regression", "backend"],
  "components": ["service-a"],
  "epic_link": "PROJ-100",
  "parent_key": null,
  "story_points": 5,
  "linked_issues": [
    { "key": "PROJ-120", "type": "blocks", "direction": "outward" }
  ],
  "subtasks": ["PROJ-124", "PROJ-125"],
  "commits": [
    { "sha": "abc123", "message": "fix: PROJ-123 null-check", "author": "alice", "date": "..." }
  ],
  "pull_requests": [
    { "id": 456, "url": "...", "state": "open" }
  ],
  "comments": [
    { "author": "alice", "created": "...", "body": "..." }
  ],
  "attachments": ["screenshot.png"],
  "acceptance_criteria": "...",
  "canonical_status": "pending",
  "canonical_reason": null
}
```

## Issue Index (`cache/issues/index.json`)

```json
{
  "last_sync": "2026-04-17T10:00:00Z",
  "provider": "jira",
  "project_keys": ["PROJ", "INFRA"],
  "count": 1250,
  "canonical_count": 420,
  "keys": ["PROJ-1", "PROJ-2", "..."]
}
```

---

## Wiki Cache (`cache/wiki/<page_id>.json`)

```json
{
  "page_id": "123456",
  "url": "https://wiki.example.com/pages/123456",
  "title": "Architecture Overview",
  "space": "Engineering",
  "space_key": "ENG",
  "content": "cleaned full text...",
  "headings": ["Overview", "Services", "Data Flow"],
  "sections": [
    { "heading": "Overview", "content": "..." }
  ],
  "code_blocks": [
    { "language": "yaml", "code": "..." }
  ],
  "tables": [ ... ],
  "images": ["img_001.png"],
  "child_pages": ["123457", "123458"],
  "parent_page": null,
  "breadcrumb": ["Engineering", "Architecture"],
  "labels": ["architecture", "canonical"],
  "last_modified": "2026-04-10T08:00:00Z",
  "cached_at": "2026-04-17T10:30:00Z",
  "cache_version": 2
}
```

---

## Video Intelligence Chunk (`cache/video_intelligence/<slug>/chunk_<n>.md`)

```markdown
---
source_type: training
topic: Architecture Deep Dive
timestamp: 00:04:30 - 00:09:15
source_video: training-session-001.mp4
chunk_index: 2
total_chunks: 12
---

## Summary
Two-sentence summary.

## Key Facts
- Fact 1
- Fact 2

## Decisions
- Decision 1

## Action Items
- Action 1

## People
- Alice Smith (Platform Lead)
- Bob Jones (SME)

## Systems
- service-a
- service-b

## Dates
- 2026-05-01: go-live target

## Questions
- Q: "How does retry work?"  A: "Exponential backoff, 3 attempts."
- Q: "What's the SLA?"  (unanswered)

## Transcript
(Full transcript of this chunk.)
```

## Video Intelligence Manifest (`cache/video_intelligence/manifest.json`)

```json
{
  "version": 1,
  "parsed": {
    "<sha256-prefix>": {
      "path": "videos/training-session-001.mp4",
      "size": 123456789,
      "mtime": 1705315800,
      "slug": "architecture-deep-dive",
      "chunks": 12,
      "parsed_at": "2026-04-17T10:30:00Z"
    }
  }
}
```

---

## Knowledge Graph (`cache/graph/graph.json`)

NetworkX node-link format with custom metadata:

```json
{
  "directed": true,
  "multigraph": false,
  "graph": {},
  "nodes": [
    {
      "id": "service-a",
      "type": "repo",
      "label": "service-a",
      "metadata": {
        "summary": { ... },
        "indexed_at": "...",
        "path": "/path/..."
      }
    },
    {
      "id": "service-a:com.example.api",
      "type": "package",
      "label": "com.example.api",
      "metadata": { "parent_repo": "service-a" }
    },
    {
      "id": "service-a:com.example.api.UserController",
      "type": "class",
      "label": "UserController",
      "metadata": {
        "fq_name": "com.example.api.UserController",
        "package": "com.example.api",
        "file_path": "src/.../UserController.java",
        "class_type": "controller"
      }
    },
    {
      "id": "service-a:com.example.api.UserController:getUser",
      "type": "method",
      "label": "getUser(Long)",
      "metadata": { "parent_class": "service-a:com.example.api.UserController" }
    },
    {
      "id": "service-a:/api/users/{id}",
      "type": "api_endpoint",
      "label": "GET /api/users/{id}",
      "metadata": { "method": "GET", "path": "/api/users/{id}" }
    },
    {
      "id": "dep:org.springframework:spring-web",
      "type": "dependency",
      "label": "spring-web",
      "metadata": { "artifact": "org.springframework:spring-web" }
    }
  ],
  "links": [
    { "source": "service-a",                              "target": "service-a:com.example.api",            "type": "contains",   "confidence": "EXTRACTED", "weight": 1.0 },
    { "source": "service-a:com.example.api",              "target": "service-a:com.example.api.UserController", "type": "contains", "confidence": "EXTRACTED", "weight": 1.0 },
    { "source": "service-a:com.example.api.UserController","target": "service-a:/api/users/{id}",            "type": "exposes",    "confidence": "EXTRACTED", "weight": 1.0 },
    { "source": "service-a:com.example.api.UserController:getUser", "target": "service-a:com.example.service.UserService:findById", "type": "calls", "confidence": "EXTRACTED", "weight": 1.0 },
    { "source": "service-a",                              "target": "dep:org.springframework:spring-web",   "type": "depends_on", "confidence": "EXTRACTED", "weight": 1.0 }
  ],
  "_meta": {
    "saved_at": "2026-04-17T10:35:00Z",
    "node_count": 450,
    "edge_count": 1200,
    "stats": { "density": 0.011, "nodes_by_type": { ... }, "edges_by_type": { ... } }
  }
}
```

### Node Types

| Type | Examples |
|------|----------|
| `repo` | `service-a` |
| `package` | `service-a:com.example.api` |
| `class` | `service-a:com.example.api.UserController` |
| `method` | `service-a:...:getUser` |
| `function` | (for languages without classes) |
| `interface` | `service-a:...:Repository` |
| `enum` | `service-a:...:SomeEnum` |
| `constant` | `service-a:...:MAX_RETRIES` |
| `api_endpoint` | `service-a:/api/users/{id}` |
| `dependency` | `dep:org.springframework:spring-web` |

### Edge Types

| Type | Semantics |
|------|-----------|
| `contains` | structural nesting (repo → package → class) |
| `exposes` | class exposes API endpoint |
| `imports` | source import |
| `extends` | class extends class |
| `implements` | class implements interface |
| `calls` | method A calls method B (EXTRACTED via AST; INFERRED via regex) |
| `references` | mentions in comment / wiki / issue |
| `uses` | generic usage (fallback) |
| `depends_on` | build-file dependency |

### Confidence

| Tag | Meaning |
|-----|---------|
| `EXTRACTED` | found via direct AST parse |
| `INFERRED` | regex/pattern match (less reliable) |
| `AMBIGUOUS` | needs human review (the analyzer surfaces these) |

---

## Analysis Report (`cache/graph/GRAPH_REPORT.md`)

```markdown
# Knowledge Graph Report

Generated: 2026-04-17T10:35:00Z
Context: <name>

## Stats
- Nodes: 450
- Edges: 1200
- Density: 0.011
- Nodes by type: { repo: 10, package: 45, class: 150, method: 220, api_endpoint: 25 }
- Edges by type: { contains: 505, exposes: 25, calls: 600, extends: 30, implements: 40 }

## God Nodes (Core Abstractions)
1. `UserService` — degree 28, PageRank 0.045, betweenness 0.12
2. `ConfigRepository` — degree 24, PageRank 0.038
...

## Communities
- **Community 1 (15 nodes):** API controllers, DTOs, services
- **Community 2 (12 nodes):** Data access layer
...

## Surprising Connections
- `service-a/FooService` → `service-b/BarProcessor` (cross-repo, INFERRED, low confidence)

## Suggested Investigations
- Review ambiguous edge: `service-a:Service` → unknown external API
- `BridgeProcessor` spans two communities — worth documenting
```

---

## Context.ini (per-context config)

See `03-install-setup/install-wizard-config.md` for the canonical shape and all section keys.

---

## Browser Server Info (`.browser-server.json`)

```json
{
  "port": 9222,
  "pid": 12345,
  "browser": "chrome",
  "user_data_dir": "_config/playwright/chrome-profile",
  "started": 1705315800.123
}
```

## Token Cache (`_config/playwright/.auth/oauth_tokens.json`)

```json
{
  "<client_id>@<hostname>@<env>": {
    "access_token": "...",
    "expires_at": "2026-04-17T11:00:00Z",
    "token_type": "Bearer",
    "scope": "openid"
  }
}
```

---

## Hash Index (`chromadb/<collection>_hashes.json`)

```json
{
  "issue_PROJ-123": "sha256-of-content-and-metadata",
  "wiki_page_456": "..."
}
```

## Progress File (`install.py` + long-running commands)

```json
{
  "phase": "dependencies",
  "percent": 42,
  "message": "Installing chromadb (this may take several minutes)...",
  "timestamp": "2026-04-17T10:05:00Z"
}
```

---

## Invariants

- **Every cache file is self-describing** — has an `indexed_at`/`cached_at` / `generated_at` timestamp and (where applicable) `cache_version` for future migrations.
- **Nothing authenticated persists unless explicitly allowed** per the data-caching policy (see `04-providers/README.md`).
- **All IDs are stable** — derived deterministically from source (repo name + fq name for graph nodes; issue key for issues; page id for wiki).
- **All embedded content is cleaned text**, not raw HTML. If the source is HTML, the ingester strips it (preserving structure in `sections` / `code_blocks`).
