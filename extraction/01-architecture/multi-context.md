# Multi-Context Architecture & Data Flow

## The Context Abstraction

A **context** is an isolated ecosystem: its own repositories, caches, issue-tracker data, wiki data, RAG index, knowledge graph, and configuration. One installation hosts N contexts. Contexts never implicitly share data.

### Why Contexts

- **Team isolation**: Team A's JIRA project keys / wiki spaces / Splunk indices differ from Team B's. Dumping them into one cache means Team A's RAG query returns irrelevant Team B hits.
- **Domain isolation**: A platform context (core services) and a product context (a specific product line) have different vocabularies. Separate graphs surface separate god-nodes.
- **Partial setup**: A user can populate context A fully while context B is empty. Each context is valid independently.
- **Safe experimentation**: Rebuilding the RAG for context A doesn't touch context B.

### What Lives Per-Context

| Per-context | Path |
|-------------|------|
| Repositories (git clones) | `contexts/<name>/repositories/` |
| Caches (repo, issues, wiki, video intel, graph) | `contexts/<name>/cache/` |
| RAG vector index | `contexts/<name>/chromadb/` |
| Context config | `contexts/<name>/config/context.ini` |
| Repository URL list | `contexts/<name>/config/repositories/<name>.txt` |
| Per-context AI reference | `contexts/<name>/CLAUDE.md` |
| Per-context knowledge | `contexts/<name>/config/knowledge/` |
| Refined domain data (optional) | `contexts/<name>/refined/` |

### What Lives Global

| Global | Path |
|--------|------|
| Defaults | `_config/defaults.ini` |
| Known contexts | `_config/known_contexts/` |
| Log-search mappings (per service) | `_config/log_search/` (generalized from `_config/splunk/`) |
| Voice/persona | `_config/voice/` |
| Global knowledge | `_config/knowledge/` |
| Shared browser profile | `_config/playwright/chrome-profile/` |
| Ephemeral auth artifacts | `_config/playwright/.auth/` |
| Dashboard assets | `dashboard/` |
| Linked-project registry | `_config/linked_projects.json` |

## Active Context

A single context is "active" at any time. Switch with `context use <name>`. Any command without `--context` uses the active context. This is stored in a small index file (e.g., `_config/active_context`) rather than in shell state, so AI assistants see the same active context.

## Cross-Context Operations

```
<tool> rag search-all "<query>"               # query every context's RAG
<tool> context <name> <cmd>                   # run a command inside a specific context without switching
```

Cross-context RAG (see `05-modules/core-modules.md`) instantiates a `RAGEngine` per context, runs each search, merges/sorts by score, tags each result with the source context.

## Data Flow

### High-Level Pipeline

```
Providers (issue tracker, source control, log search, wiki, APIs)
      │
      ▼
  sync ──────┐
      │      │
      ▼      ▼
  clone/     cache JSON   ← JSON files on disk, readable without the tool
  pull           │
  repos          ▼
      │      indexer/post-sync hooks
      ▼          │
  filesystem     ▼
      │      RAG indexer + Graph builder
      ▼          │
  ChromaDB ◄─────┤
      │      Graph JSON ◄──┐
      ▼          │         │
  queries (rag, query, graph, dashboard, skills)
```

### Sync Phase

`SyncManager.sync(sources=[...], full=...)`:
1. Pulls/clones repos via `CacheManager`.
2. Fetches issue-tracker updates via issue-provider skill.
3. Fetches wiki updates via wiki-provider skill.
4. Triggers post-sync hooks (per-repo processors in `scripts/repo_post_sync/`).
5. If auto-RAG enabled, triggers RAG rebuild.
6. Updates `contexts/<name>/cache/sync_status.json` with per-source result + duration + counts.

### Cache Phase

`GlobalIndexer.index_all()`:
1. For each cloned repo, `RepoIndexer.index()` walks the file tree, extracts classes/methods/APIs/dependencies, writes `cache/repos/<repo>.json`.
2. Aggregates cross-repo: `cache/indexes/apis.json`, `cache/indexes/source_map.json`, `cache/indexes/global_index.json`.

### RAG Phase

`MasterIndexer.index_all()`:
1. Per-source indexers (issue, wiki, repo, git-history, architecture docs, video intelligence) produce `Document` objects.
2. `TextChunker` splits each into chunks (heading/function-aware).
3. `EmbeddingBackend` (ONNX+CoreML → MPS → CPU fallback) embeds chunks.
4. `RAGEngine.add_documents()` writes into ChromaDB.
5. Hash index (`chromadb/*_hashes.json`) dedupes future runs.

### Graph Phase

`GraphBuilder.build(use_treesitter=True)`:
1. Load `cache/repos/*.json`; create repo/package/class/api nodes + `contains`/`exposes` edges.
2. (Optional) Run tree-sitter AST extractor on source; add method/import/call/inheritance nodes+edges.
3. Pattern-match cross-service REST calls; add inferred `calls` edges (tagged `INFERRED`).
4. Save `cache/graph/graph.json` + timestamped snapshot.
5. `GraphAnalyzer.full_analysis()` computes god nodes (centrality), communities (Leiden→Louvain→label propagation), surprising cross-community edges, suggested investigations. Writes `cache/graph/GRAPH_REPORT.md`.

### Query Phase

- **RAG**: `RAGEngine.search(query)` embeds query, ChromaDB top-N, optionally boosts via `GraphRAGBridge` using god-node importance.
- **Query (structured)**: reads JSON caches directly — zero dependencies.
- **Graph**: `GraphAnalyzer.god_nodes() / communities() / surprising_connections()`.
- **Skills**: dispatch to a registered skill (uses caches + optional live API calls).

## Freshness Model

Each sync source records its last run in `cache/sync_status.json`:

```json
{
  "repos":  { "last_sync": "...", "last_result": "success", "duration_seconds": 45.2, "repos_updated": 12, "repos_failed": 0 },
  "issues": { "last_sync": "...", "last_result": "success", "issues_updated": 250 },
  "wiki":   { "last_sync": "never" },
  "rag":    { "last_sync": "...", "last_result": "success", "documents_added": 320 }
}
```

`sync --status` reads this file and prints a freshness report. Users should prefer `--status` to auto-syncing on every invocation.

## Isolation Boundaries

- Repositories from context A live only in `contexts/A/repositories/`. If context B references the same git URL, it is cloned a second time into `contexts/B/repositories/`. Disk cost is real; isolation cost is low.
- RAG collections are per-context; ChromaDB is a separate persistent client per context path.
- Graphs are per-context; cross-context graph queries are not supported (intentional — communities are only meaningful within a coherent ecosystem).
- Auth is **shared** across contexts (one SSO session, one OAuth token cache). This is pragmatic — users authenticate with one identity regardless of context.
