# Core Modules

The engines that make the tool useful: RAG, knowledge graph, cache/context/sync managers, indexer, CDP watcher, auth, dashboard.

Each section gives purpose, key classes/signatures, data model, integration points, and pluggability notes. This is the implementation spec — a developer should be able to rebuild each module from its section.

---

## 1. RAG Engine

**Location**: `scripts/rag/`

### Purpose

Semantic search over the combined corpus (issues, wiki, repos, git history, architecture docs, video intelligence). Consumers call `RAGEngine.search()` or `get_context()` to augment LLM prompts with retrieved text.

### Key Classes

```python
class RAGEngine:
    def __init__(self, base_path: str = "cache/rag",
                 collection_name: str = "<tool>_docs",
                 context: Optional[str] = None,
                 embedding_model: str = "all-MiniLM-L6-v2",
                 chunk_size: int = 750,
                 chunk_overlap: int = 150): ...

    def add_documents(self, documents: list[Union[dict, Document]],
                      skip_duplicates: bool = True,
                      batch_size: int = 100) -> dict:
        # Returns {added, skipped, chunks, errors}

    def search(self, query: str, n_results: int = 10,
               filters: Optional[dict] = None,
               include_content: bool = True,
               query_embedding: Optional[list[float]] = None) -> list[SearchResult]:
        # Top-N by cosine similarity (score 0.0–1.0)

    def get_context(self, query: str, max_tokens: int = 2000,
                    filters: Optional[dict] = None,
                    format_style: str = "detailed") -> str:
        # Returns formatted markdown string, respecting token budget

    def clear(self, confirm: bool = False) -> bool: ...
    def stats(self) -> dict: ...
```

```python
@dataclass
class Document:
    id: str
    content: str
    metadata: dict             # source, indexed_at, custom

@dataclass
class SearchResult:
    id: str
    content: str
    metadata: dict
    score: float               # 0..1 cosine similarity
    distance: float            # raw
```

```python
class TextChunker:
    def __init__(self, chunk_size=750, chunk_overlap=150, min_chunk_size=100): ...
    def chunk_document(self, doc_id: str, content: str,
                       metadata: dict) -> list[ChunkInfo]:
        # Strategies:
        #  - "code"       → chunk by function/class boundaries
        #  - "structured" → chunk by heading
        #  - "plain"      → chunk by sentence/paragraph
        # Strategy auto-detected from metadata["source_type"].
```

```python
@dataclass
class ChunkInfo:
    chunk_id: str
    parent_id: str
    content: str
    chunk_index: int
    total_chunks: int
    metadata: dict
```

### Embedding Backends (`embedding_backends.py`)

```python
class EmbeddingBackend(ABC):
    def encode(self, texts: list[str], show_progress=False) -> list[list[float]]: ...
    def is_available(self) -> bool: ...

def detect_best_backend() -> EmbeddingBackend:
    # Priority:
    #   1. ONNX + CoreML (macOS arm64, ~10-20x faster)
    #   2. sentence-transformers + MPS (macOS arm64 fallback)
    #   3. sentence-transformers + CPU (universal)
    #   4. Remote API-compatible backend (optional plugin)
```

### Source-Specific Indexers (`indexers.py`)

Each source type is an indexer that returns `list[Document]`:

```python
class MasterIndexer:
    def __init__(self, base_path: Path, context: str): ...
    def index_all(self) -> list[Document]:
        # Aggregates:
        #   IssueIndexer (cache/issues/*.json)
        #   WikiIndexer (cache/wiki/*.json)
        #   RepoIndexer (cache/repos/*.json)
        #   GitHistoryIndexer (repositories/*/.git)
        #   ArchitectureIndexer (cache/architecture/*.md)
        #   VideoIntelligenceIndexer (cache/video_intelligence/*.md)
```

Each indexer produces `Document` objects with metadata tagged by `source_type` so the chunker picks the right strategy.

Factory helpers:
```python
create_issue_document(issue: dict) -> Document
create_wiki_document(page: dict) -> Document
create_code_document(file_path: str, content: str, repo: str, language: str) -> Document
create_git_history_document(commit: dict) -> Document
```

Adding a new source = new indexer subclass + new factory.

### Cross-Context RAG (`cross_context_rag.py`)

```python
class CrossContextRAG:
    def search(self, query: str, n_results_per_context: int = 10,
               contexts: Optional[list[str]] = None) -> list[SearchResult]:
        # Instantiates RAGEngine per context, runs each, merges, sorts by score,
        # annotates each result with source context.
```

### Data Model

**ChromaDB collection** (persistent at `contexts/<name>/chromadb/`):

```json
{
  "ids": ["issue_PROJ-123", "issue_PROJ-123__chunk_1", "..."],
  "embeddings": [[...], ...],
  "documents": ["# PROJ-123: title\n...", ...],
  "metadatas": [
    {
      "source_type": "issue",
      "key": "PROJ-123",
      "project": "PROJ",
      "status": "In Progress",
      "parent_id": "issue_PROJ-123",
      "chunk_index": 0,
      "total_chunks": 2,
      "indexed_at": "2026-04-17T10:30:00Z"
    }
  ]
}
```

**Hash index** (`chromadb/<collection>_hashes.json`):
```json
{
  "issue_PROJ-123": "sha256-of-content-and-metadata",
  "wiki_page_456":  "..."
}
```
Used to skip re-embedding unchanged documents.

### Integration

- Writers: `MasterIndexer` (invoked from `rag index`, `sync --rag`).
- Readers: `RAGSkill` (CLI `rag search/context/stats`), `CrossContextRAG`, `GraphRAGBridge`.
- Storage: ChromaDB PersistentClient at `contexts/<name>/chromadb/`.

### Design Decisions

- **Chunks carry parent id** — `get_document(parent_id)` can reassemble the full document when needed.
- **Lazy model load** — no startup cost; embedder loaded on first search or ingest.
- **Graceful fallback** — if ChromaDB isn't installed, `RAGSkill` returns an error with the install hint instead of crashing.
- **Metadata sanitization** — ChromaDB only accepts str/int/float/bool in metadata; lists/dicts get CSV/JSON-encoded.
- **Graph bridge is optional** — if `cache/graph/graph.json` exists, results get re-ranked by graph importance; if not, raw similarity.

### Pluggability

- Swap embedding backend by subclassing `EmbeddingBackend`.
- Swap vector store by subclassing the storage layer in `rag_engine.py` (only the `add_documents`/`search` methods touch ChromaDB directly — refactor those behind an interface to support Qdrant, pgvector, Weaviate, FAISS, etc.).
- Add a new source by writing a new indexer + document factory.

---

## 2. Knowledge Graph

**Location**: `scripts/graph/`

### Purpose

A directed graph of the codebase: nodes are repos/packages/classes/methods/APIs/dependencies; edges are containment/imports/calls/implements/exposes/depends_on. Enables architectural questions RAG can't cleanly answer: "what are the god nodes?", "what are the communities?", "what cross-domain call is suspicious?".

### Key Classes

```python
class GraphBuilder:
    def __init__(self, context_path: Path): ...
    def build(self, use_treesitter: bool = True,
              include_external_deps: bool = False) -> nx.DiGraph:
        # Phase 1: load cache/repos/*.json → repo/package/class/api nodes + contains/exposes edges
        # Phase 2 (opt): tree-sitter AST → method nodes + imports/calls/extends/implements edges
        # Phase 3: pattern-match REST calls between services → inferred "calls" edges
    def save(self, graph: nx.DiGraph, path: Optional[Path] = None) -> Path: ...
    def load(self, path: Optional[Path] = None) -> nx.DiGraph: ...
    def graph_stats(self, graph: nx.DiGraph) -> dict: ...
```

```python
class GraphAnalyzer:
    def god_nodes(self, k: int = 15) -> list[tuple[str, float]]:
        # Top-K by (degree + PageRank + betweenness) / 3
    def communities(self) -> dict[str, list[str]]:
        # Leiden (preferred) → Louvain → label propagation
    def surprising_connections(self) -> list[tuple[str, str, float]]:
        # Cross-community edges scored by unexpectedness
    def suggested_questions(self) -> list[str]:
        # Investigations: ambiguous edges, bridges, orphans
    def full_analysis(self) -> dict: ...
```

```python
class GraphDiff:
    def compare(self, old_snapshot: Path, new_snapshot: Path) -> dict:
        # {added_nodes, removed_nodes, modified_nodes, added_edges, removed_edges}

class GraphExporter:
    def export_html(self, graph, path): ...       # vis.js, dark theme, search, community colors
    def export_graphml(self, graph, path): ...    # Gephi / yEd
    def export_cypher(self, graph, path): ...     # Neo4j import script
    def export_json(self, graph, path): ...
    def export_report(self, graph, analysis, path): ...  # markdown summary

class TreesitterExtractor:
    def extract_from_repo(self, repo_path: Path) -> dict[str, Any]: ...
    # Returns {repo_name: {classes: [{name, methods, imports}], ...}}
```

```python
class GraphRAGBridge:
    # Called by RAGEngine.search if a graph is available.
    # Boosts scores of results whose source entities are high-importance graph nodes.
    def boost(self, results: list[SearchResult]) -> list[SearchResult]: ...
```

### Data Model

See `08-data-models/schemas.md` for the complete graph JSON shape. Summary:

- Node IDs are `<repo>:<fq_name>` for deterministic dedup.
- Each edge carries `confidence` ∈ `{EXTRACTED, INFERRED, AMBIGUOUS}` so the analyzer and visualizer can style/filter.
- Timestamped snapshots go into `cache/graph/snapshots/<iso>.json` for `graph diff`.

### Integration

- `SyncManager` can trigger graph build after repo cache generation (off by default, opt-in per context).
- `graph_skill.py` exposes CLI `graph build/analyze/export/diff`.
- `GraphRAGBridge` plugs into RAG query pipeline.
- Dashboard reads `cache/graph/graph.json` for the vis.js visualization page.

### Pluggability

- **Language support**: tree-sitter backends (Java, Python, TypeScript/JavaScript, Go, Rust, Kotlin, C#). Extensible by adding more `tree-sitter-*` packages and pattern rules.
- **Community detection**: `Leiden → Louvain → label-propagation` fallback chain. Add others by subclassing `CommunityDetector`.
- **REST call inference**: pattern rules live in `graph_builder.py`; extend for different HTTP clients (RestTemplate, WebClient, axios, requests, ktor-client, etc.).

---

## 3. Cache / Context / Sync Managers

**Location**: `scripts/cache_manager.py`, `scripts/context_manager.py`, `scripts/sync_manager.py`, `scripts/link_manager.py`, `scripts/known_context_loader.py`, `scripts/workdir.py`

### CacheManager

```python
class CacheManager:
    def __init__(self, base_path: Optional[Path] = None,
                 context: Optional[str] = None): ...
    def load_repository_configs(self) -> list[dict]: ...
    def get_all_repo_configs(self) -> list[tuple[str, Optional[str]]]: ...
    def extract_repo_name(self, url: str) -> str: ...
    def get_repo_path(self, url: str) -> Path: ...
    def clone_repo(self, url: str, force: bool = False) -> tuple[bool, str]: ...
    def pull_repo(self, url: str,
                  branch_override: Optional[str] = None) -> tuple[bool, str]: ...
    def pull_all(self) -> dict:                       # {success: [...], failed: [...]}
        ...
    def cache_repo(self, repo_path: Path) -> dict:    # writes cache/repos/<name>.json
        ...
    def cache_all(self) -> dict: ...
```

Certificate propagation: set `GIT_SSL_CAINFO`, `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE`, `CURL_CA_BUNDLE` from `netscope.pem` (or equivalent) so all subprocesses inherit the corporate CA bundle.

Retry logic: 3 attempts, exponential backoff. Distinguishes transient (network) vs permanent (auth) failures — only retry transient.

### ContextManager / ContextConfig

```python
class ContextConfig:
    def __init__(self, name: str, base_path: Path): ...
    def exists(self) -> bool: ...
    def load(self) -> None: ...                        # parse context.ini
    def save(self) -> None: ...
    def get(self, section: str, key: str, fallback=None): ...
    def set(self, section: str, key: str, value: str): ...
    # provider-agnostic convenience accessors:
    def get_issue_tracker_config(self) -> dict: ...
    def get_wiki_config(self) -> dict: ...
    def get_log_search_config(self) -> dict: ...
    def get_repository_groups(self) -> list[str]: ...
    def get_metadata(self) -> ContextMetadata: ...
    # well-known paths:
    context_root: Path
    config_path: Path
    repositories_path: Path
    cache_path: Path
    chromadb_path: Path

class ContextManager:
    def list_contexts(self) -> list[str]: ...
    def get_active_context(self) -> str: ...
    def set_active_context(self, name: str) -> None: ...
    def get_context_config(self, name: str) -> ContextConfig: ...
    def create_context(self, name: str, display_name: str,
                       description: str) -> ContextConfig: ...
    def delete_context(self, name: str, confirm: bool = False) -> bool: ...
```

### SyncManager

```python
class SyncManager:
    def __init__(self, context_name: str, base_path: Path): ...
    def sync(self, sources: Optional[list[str]] = None,
             full: bool = False) -> SyncResult: ...
    def get_freshness_report(self) -> dict[str, str]: ...

    # Private:
    def _sync_repos(self, full: bool) -> SyncSourceStatus: ...
    def _sync_issues(self, full: bool) -> SyncSourceStatus: ...
    def _sync_wiki(self, full: bool) -> SyncSourceStatus: ...
    def _sync_rag(self, rebuild: bool) -> SyncSourceStatus: ...
    def _run_repo_post_sync_hooks(self, repos_dir: Path) -> dict: ...
```

```python
@dataclass
class SyncResult:
    context: str
    started_at: str
    completed_at: str
    sources_synced: list[str]
    results: dict[str, SyncSourceStatus]
    overall_status: Literal["success", "partial", "failed"]
    rag_auto_rebuilt: bool
```

Sync config (section `[sync]` of context.ini):
```ini
[sync]
default_sources = repos,issues
full_sources = repos,issues,wiki,rag
issues_update_mode = incremental
issues_update_since = -1w
wiki_urls = https://wiki.example.com/space/TEAM
wiki_max_pages = 500
auto_rag_rebuild = true
```

### WorkDir

```python
class WorkDir:
    def context_dir(self, ctx: str) -> Path: ...
    def shared_dir(self) -> Path: ...
    def get_temp_path(self) -> Path: ...
    def get_temp_file(self, suffix: str = "") -> Path: ...
    def cleanup_old_files(self, max_age_hours: int = 24) -> int: ...
```

All temp files go through `WorkDir` so sandbox-safe directories (`$TMPDIR`) are used consistently.

### Design Decisions

- **File-based credential helper** for git (`.git-credentials`) rather than keychain — works from AI sandboxes.
- **Parallel clone/pull** with `parallel_workers` from config (default 4).
- **Post-sync hooks** per repo — extension point. Example: regenerate Claude Code slash commands based on repo artifacts.
- **Auto-RAG opt-in** — sync does NOT rebuild RAG unless `auto_rag_rebuild = true` or `--rag` passed.
- **Partial failure tolerance** — one repo failing doesn't abort the whole sync.

---

## 4. Indexer & Repo Post-Sync

**Location**: `scripts/indexer.py`, `scripts/repo_post_sync/`

### RepoIndexer

Walks a single repo's filesystem and extracts structured metadata:

```python
class RepoIndexer:
    def __init__(self, repo_path: Path): ...
    def index(self) -> dict:
        # {
        #   name, path, indexed_at,
        #   summary: {total_files, source_files, controllers, services, repositories, tests},
        #   structure: {dirs: {...}, files: [...]},      # nested tree
        #   source_files: [{path, package, class, lines, hash, extension}, ...],
        #   apis: [{method, path, file}, ...],
        #   services: [{name, path}, ...],
        #   models: [{name, path}, ...],
        #   dependencies: [{type, artifact}, ...],
        #   build: {type, version, file},
        #   readme: "..."
        # }
```

**Extraction patterns** are a registry of globs + regexes per language/framework. Shipped patterns (extend as needed):

- Spring controllers (`@GetMapping`, `@PostMapping`, `@RestController`)
- Express/Koa routes (`app.get('/path', ...)`)
- FastAPI routes (`@app.get`, `@router.post`)
- Flask routes (`@app.route`)
- Maven (`pom.xml`) / Gradle (`build.gradle[.kts]`) / npm (`package.json`) / Python (`pyproject.toml`, `setup.py`) / Cargo / Go modules

Skipped directories (speed): `.git`, `node_modules`, `target`, `build`, `dist`, `__pycache__`, `.idea`, `.vscode`.

### GlobalIndexer

Orchestrates across all repos for a context:

```python
class GlobalIndexer:
    def __init__(self, cache_dir: Path, repos_dir: Path): ...
    def index_all(self) -> dict:
        # For each repo: RepoIndexer(repo).index() → cache/repos/<name>.json
        # Aggregate:
        #   cache/indexes/apis.json           # all APIs grouped by repo
        #   cache/indexes/source_map.json     # source file map
        #   cache/indexes/global_index.json   # master index
```

### Post-Sync Hooks

Extension point. A hook is a Python module in `scripts/repo_post_sync/` with a `run(repo_path, context) -> dict` function. Sync calls all hooks for each repo after pulling. Return value is merged into the sync status report.

Example (the original had `specification_commands.py` which regenerated Claude Code slash commands from a docs-template repo):

```python
def run(repo_path: Path, context: ContextConfig) -> dict:
    if not (repo_path / "docs-template").exists():
        return {"skipped": True}
    return regenerate_claude_commands(repo_path / "docs-template")
```

Hooks must be idempotent and fast (<5s typical). Slow hooks should be skipped unless `--full`.

---

## 5. CDP Browser Server & Watcher

**Location**: `scripts/browser_server.py`, `scripts/dispatch_*.py`

### Purpose

A persistent Chrome/Edge browser running under Chrome DevTools Protocol (CDP). Playwright-based skills connect to it over `localhost:<port>` instead of each launching their own browser. Two benefits:

1. **One SSO session reused across skills** — no re-auth per query.
2. **Process isolation** — the watcher runs outside the AI-assistant sandbox, where it can access the keychain, spawn browsers, and handle auth. The sandbox-bound CLI dispatches requests to it.

### Watcher Dispatch Pattern

```
CLI (in sandbox)                 Watcher (outside sandbox)
    │                                  │
    │ <tool> server dispatch <cmd>     │
    │   write request JSON to          │
    │   watcher inbox dir              │
    ├─────────────────────────────────▶│
    │                                  │ detect new file
    │                                  │ execute the command
    │                                  │ (browse, auth, query)
    │                                  │ write result JSON
    │ poll watcher outbox              │
    │◀─────────────────────────────────┤
```

Inbox/outbox live in `WorkDir.shared_dir()`. The watcher polls or uses `fsnotify`/`watchdog`. Request/response files have short-lived tokens to pair them.

### browser_server.py CLI

```bash
<tool> server start [--port N] [--foreground]
<tool> server stop
<tool> server status
<tool> server diagnose            # auto-repair (kill stuck processes, clear lockfiles)
<tool> server ps [pattern]
<tool> server kill <pid|pattern> [-9]
<tool> server watch               # foreground watcher loop
<tool> server dispatch <cmd> [--arg value ...]
```

### Server Info File

`.browser-server.json` at installation root:
```json
{
  "port": 9222,
  "pid": 12345,
  "browser": "chrome",
  "user_data_dir": "_config/playwright/chrome-profile",
  "started": 1705315800.123
}
```

### Chrome Launch Flags

```
--remote-debugging-port=<port>
--user-data-dir=<shared_profile>
--headless=new                           (omit for --visible)
--disable-blink-features=AutomationControlled
--auth-server-whitelist=<comma-separated hosts>
--auth-negotiate-delegate-whitelist=<...>
--disable-features=ChromeLabs,PrivacySandboxSettings4
```

The auth whitelist is **per context** (hosts your org's SSO uses for Windows Integrated Auth / Kerberos). Configure via `[server]` section in `_config/defaults.ini`.

### On macOS

The installer writes a LaunchAgent at `~/Library/LaunchAgents/com.<tool>.browser-server.plist` so the watcher auto-starts on login. User can disable via `launchctl unload`.

### On Windows

A scheduled task or a shortcut in `shell:startup`. Edge is preferred on Windows for Windows Integrated Auth (Kerberos delegation "just works").

### On Linux

A systemd user unit at `~/.config/systemd/user/<tool>-browser.service`. Disabled by default — user opts in.

### ps/kill Replacement

The CLI provides `server ps` and `server kill` as sandbox-safe replacements for bare `ps` and `kill`. Some AI-assistant sandboxes deny those commands; wrapping them in the CLI (which has a permitted-commands allowlist) lets assistants manage processes without an escape hatch.

---

## 6. Auth

Covered in detail in `04-providers/README.md` (auth models, failure policy, data caching policy). Key code locations:

- `scripts/api_skills/base.py` — `OAuthApiSkillBase` with token cache + 401-auto-refresh + retries.
- `scripts/playwright_skills/oauth_token_skill.py` — acquires OAuth2 tokens via browser SSO by intercepting Authorization headers or token-endpoint responses.
- `scripts/playwright_skills/base.py` — `PlaywrightSkillBase` with CDP-first browser launch chain and shared profile management.

### Token Storage

`_config/playwright/.auth/oauth_tokens.json`:
```json
{
  "<client_id>@<hostname>@<env>": {
    "access_token": "...",
    "expires_at": "2026-04-17T11:00:00Z",
    "token_type": "Bearer",
    "scope": "..."
  }
}
```

Keyed by `client_id@hostname@env` so tokens for different environments never collide.

### Browser Profile

`_config/playwright/chrome-profile/` — persistent Chrome profile used by **all** Playwright skills. Signing into any provider signs you into all of them (as long as they share the SSO tenant). Gitignored. Nuke it with `<tool> auth reset` (implementation note — add this subcommand).

---

## 7. Dashboard

**Location**: `dashboard/server.py`

### Purpose

Local HTTP server (port 4242) that exposes a web UI for browsing contexts, caches, APIs, graph, and refined domain data. Bound to `localhost` only — never expose externally.

### API Surface

All JSON over HTTP. No auth — it's localhost-only.

```
GET /api/health
GET /api/overview                                 # list contexts, freshness, auth status
GET /api/contexts/<name>/repos
GET /api/contexts/<name>/apis
GET /api/contexts/<name>/refined/manifest         # extension point
GET /api/contexts/<name>/refined/fields?source=...&entity=...&search=...
GET /api/contexts/<name>/refined/field-values/<field_path>
GET /api/contexts/<name>/refined/correlations?source=...&field=...
GET /api/contexts/<name>/refined/sources
GET /api/contexts/<name>/refined/entity-tree
GET /api/contexts/<name>/viz/graph                # knowledge graph
GET /api/contexts/<name>/viz/communities
GET /api/contexts/<name>/viz/entity/<id>
```

### HTML Assets

- `dashboard/index.html` — main overview (context cards, cache freshness, auth status).
- `dashboard/viz.html` — vis.js graph page.
- `dashboard/context-dashboard-template.html` — per-context domain explorer (copied into `contexts/<name>/dashboard/index.html` when a context needs custom views).

### Design

- Static HTML with vanilla JS calling the JSON endpoints. No SPA framework — keeps the stack tiny.
- vis.js (CDN or vendored) for the graph visualization.
- In-memory caching of large files (unique-values, correlations) per server lifetime.

### Launch

```
<tool> dashboard           # starts server on :4242 and opens browser
```

---

## 8. Video Intelligence (Optional)

**Location**: `scripts/skills/video_intel_skill.py`, `scripts/skills/video_to_doc_skill.py`, `scripts/skills/transcribe_skill.py`

Included because it's one of the more distinctive capabilities and people asked about it. Out-of-scope for the minimum viable build, but design is worth preserving.

### Video → Intelligence

1. Extract audio with `ffmpeg`.
2. Transcribe with Whisper (MLX-Whisper on Apple Silicon, faster-whisper on CPU — see `06-skills/skills-catalog.md`).
3. Extract key frames (scene-change detection).
4. Chunk transcript; feed chunks to local LLM (MLX-LM or Ollama) with a structured-extraction prompt that returns:
   ```json
   {"source_type": "...", "topic": "...", "key_facts": [...], "decisions": [...],
    "action_items": [...], "people": [...], "systems": [...],
    "dates": [...], "questions": [...], "summary": "..."}
   ```
5. Write one markdown file per chunk to `contexts/<name>/cache/video_intelligence/`.
6. RAG indexer picks those markdowns up automatically.

### Video → Doc

Converts a video or series of videos into PPTX or DOCX handouts. Uses the same transcription + keyframe pipeline, plus cross-video deduplication via sentence embeddings.

### Key Dependencies (lazy-loaded)

- `ffmpeg`, `ffprobe` (system binaries)
- `mlx-whisper` OR `faster-whisper`
- `mlx-lm` OR `ollama`
- `python-pptx`, `python-docx`, `Pillow`, `sentence-transformers`

### Path Guard

The video skill has a hard path guard: the source video must live inside the project directory unless `--force-outside-project` is passed. This is because video processing creates large temp files and the sandbox policy restricts where they can go.

---

## Minimum Build Order

If you're rebuilding from scratch:

1. `config.py` + `_config/defaults.ini`
2. `context_manager.py` + `contexts/` layout
3. `cache_manager.py` + `indexer.py`
4. One provider adapter (source-control is easiest to start with)
5. `sync_manager.py`
6. `rag/` (then chunker, indexers, engine)
7. `graph/` (then builder, analyzer, exporter)
8. `browser_server.py` + watcher
9. `dashboard/server.py`
10. Remaining provider adapters
11. Video intelligence (optional)
