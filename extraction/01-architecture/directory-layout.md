# Directory Layout

The top-level layout of a rebuilt installation. All paths relative to the installation root.

```
.
├── <tool>.py                    # Main CLI entry point (argparse dispatcher)
├── install.py                   # Bootstrap: venv, deps, browsers, certs, known-context seeding
├── pytest.ini                   # Test configuration
├── README.md                    # Project pitch + quickstart
├── CLAUDE.md                    # Authoritative AI-assistant instructions (project-level)
├── INIT.md                      # AI bootstrap instructions for linking into other projects
├── <tool>.code-workspace        # VS Code multi-folder workspace
├── netscope.pem (optional)      # Corporate CA bundle (gitignored in private deployments)
│
├── _config/                     # Global (non-context) configuration
│   ├── defaults.ini.template    # Template for user-specific defaults.ini
│   ├── context_defaults.ini     # Default settings for new contexts
│   ├── known_contexts/          # Pre-configured ecosystems (each with definition.toml, CLAUDE.md, skills, knowledge)
│   ├── knowledge/               # Global knowledge bank (markdown + JSON index)
│   ├── playwright/              # Browser profile + ephemeral auth artifacts (gitignored)
│   │   ├── .auth/               # Per-provider cookie/token dumps (gitignored)
│   │   └── chrome-profile/      # Persistent browser profile (gitignored)
│   ├── linked_projects.json     # Registry of linked external projects
│   ├── question_monitor.json    # Tracked JIRA-like questions
│   └── voice/                   # Assistant "voice" / persona configuration
│
├── lincai/                      # (Legacy single-file package OR module root for importable code)
│
├── scripts/                     # Primary implementation directory
│   ├── config.py                # Config readers (ini + toml + env overrides)
│   ├── context_manager.py       # Context lifecycle
│   ├── cache_manager.py         # Repo cache generation
│   ├── sync_manager.py          # Unified refresh orchestration
│   ├── indexer.py               # Repo → structured JSON
│   ├── link_manager.py          # Register with AI tools (Claude, Copilot)
│   ├── link_<tool>.py           # Symlink-based linking (legacy)
│   ├── known_context_loader.py  # Load pre-configured ecosystems
│   ├── migrate_to_contexts.py   # One-time migration to multi-context layout
│   ├── setup_wizard.py          # Interactive setup
│   ├── browser_server.py        # CDP Chrome/Edge watcher (auth isolation)
│   ├── skill_manager.py         # Skill registry + dispatcher
│   ├── claude_skills_manager.py # Install slash-command skills into Claude Code
│   ├── workdir.py               # Temp/work dir conventions
│   ├── ai_query.py              # AI-facing query surface (structured output)
│   ├── question_monitor.py      # Background question-tracking daemon
│   ├── report_generator.py      # Reports
│   ├── docx_generator.py        # Word output
│   ├── md_to_pdf.py             # PDF output
│   ├── md_to_docx.py            # Word output
│   ├── generate_pdf.py
│   ├── refine.py                # Content refinement utilities
│   ├── pptx_cleanup.py
│   ├── rebuild_rag.py           # Rebuild RAG index from caches
│   ├── rebuild_context_rag.py
│   ├── regenerate_gp_knowledge_base.py
│   ├── build_status.py
│   │
│   ├── skills/                  # Domain skills (swappable capabilities)
│   │   ├── __init__.py
│   │   ├── <domain>_cache_skill.py   # e.g. issue-tracker-cache, wiki-cache
│   │   ├── llm_skill.py              # Local LLM wrapper (Ollama, MLX)
│   │   ├── transcribe_skill.py       # Audio transcription (Whisper)
│   │   ├── video_intel_skill.py      # Video intelligence (scene detect, OCR, ASR)
│   │   ├── video_to_doc_skill.py     # Video → structured doc (pptx/docx)
│   │   ├── firewall_skill.py         # Egress analysis
│   │   ├── cloudwatch_skill.py       # Cloud log provider (AWS CloudWatch-like)
│   │   ├── pptx_fill_skill.py        # PowerPoint templating
│   │   └── <domain>_mapping_skill.py # Domain data mapping (extension point)
│   │
│   ├── api_skills/              # OAuth2 / REST API skills (backend services)
│   │   ├── __init__.py
│   │   ├── base.py              # OAuthApiSkillBase (auto-refresh, retries)
│   │   ├── access_control_skill.py
│   │   ├── <api>_api.py         # Per-service adapter
│   │   └── domain_knowledge.py  # Domain vocabulary (extension point)
│   │
│   ├── playwright_skills/       # Browser-based skills (SSO, scraping)
│   │   ├── __init__.py
│   │   ├── base.py              # PlaywrightSkillBase (cert, profile, auth)
│   │   ├── browser_cdp.py       # CDP client
│   │   ├── oauth_token_skill.py # Token acquisition via browser SSO
│   │   ├── <provider>_browser.py # Per-provider scraper (jira, gitlab, splunk, servicenow)
│   │   ├── network_capture.py   # Request interception
│   │   ├── header_analyzer.py   # Auth header extraction
│   │   └── extract_diagrams.py  # Confluence/wiki diagram extraction
│   │
│   ├── rag/                     # Retrieval-augmented generation
│   │   ├── __init__.py
│   │   ├── rag_engine.py        # ChromaDB wrapper, query/ingest
│   │   ├── rag_skill.py         # CLI-facing skill
│   │   ├── indexers.py          # Source-specific ingesters
│   │   ├── embedding_backends.py # Swappable embedders (HF, local, OpenAI-compat)
│   │   └── cross_context_rag.py # Query across multiple contexts
│   │
│   ├── graph/                   # Knowledge graph engine
│   │   ├── __init__.py
│   │   ├── graph_builder.py     # NetworkX DiGraph construction
│   │   ├── graph_analyzer.py    # God nodes, communities, suggestions
│   │   ├── graph_export.py      # HTML (vis.js), GraphML, Cypher, JSON, markdown
│   │   ├── graph_diff.py        # Structural diff between graph snapshots
│   │   ├── graph_rag_bridge.py  # Boost RAG results with graph importance
│   │   ├── graph_skill.py       # CLI-facing skill
│   │   ├── treesitter_extractor.py # AST extraction (swappable language backend)
│   │   └── <viz>_viz.py         # Specialized visualizations (API interconnect, pipeline)
│   │
│   ├── repo_post_sync/          # Post-sync hooks (per-context)
│   │   └── <hook>.py            # Extension point: regenerate slash commands, etc.
│   │
│   └── rfp_intake/              # Example: email intake pipeline (optional domain module)
│
├── contexts/                    # Per-context data (isolated)
│   └── <context_name>/
│       ├── config/              # Context-specific config (repositories.ini, context.ini)
│       ├── repositories/        # Cloned repos (gitignored)
│       ├── cache/               # Per-context caches
│       │   ├── repos/           # Per-repo JSON caches
│       │   ├── indexes/         # Cross-repo indexes (apis.json, global_index.json)
│       │   ├── jira/            # Issue-tracker cache (ML dataset)
│       │   ├── confluence/      # Wiki cache
│       │   └── sync_status.json # Freshness tracker
│       ├── chromadb/            # RAG vector index (gitignored)
│       ├── graph/               # Knowledge graph snapshots
│       └── context.ini          # Active context flag, display name
│
├── cache/                       # Legacy / global cache (pre-migration)
├── repositories/                # Legacy / global repo location (pre-migration)
│
├── dashboard/                   # Web dashboard
│   ├── server.py                # Flask/HTTP server (port 4242)
│   ├── index.html               # Main page (generated)
│   ├── viz.html                 # Graph visualization page
│   ├── context-dashboard-template.html
│   └── data/                    # Generated JSON served to the UI
│
├── docs/                        # Human-facing docs
│   ├── claude/                  # AI-assistant detail pages (linked from CLAUDE.md)
│   │   ├── architecture.md
│   │   ├── auth-and-security.md
│   │   ├── commands.md
│   │   ├── environment.md
│   │   ├── graph-engine.md
│   │   ├── jira-workflows.md      # Generalize: issue-tracker-workflows.md
│   │   ├── media-skills.md
│   │   ├── onboarding.md
│   │   ├── skills-reference.md
│   │   └── splunk-index-map.md    # Generalize: log-index-map.md (extension-point)
│   ├── DEVELOPER_PITCH.md
│   ├── LOCAL_LLM_SETUP.md
│   └── <optional domain docs>/
│
├── tests/                       # Pytest suite
│   ├── conftest.py              # Shared fixtures (tmp_lincai_dir, tmp_context, mocks)
│   ├── data/                    # Synthetic fixtures
│   └── test_*.py                # See 07-tests/
│
├── exports/                     # Generated archives (gitignored)
└── reports/                     # Generated reports (gitignored)
```

## Gitignored Items

- `.venv/`
- `netscope.pem` (corporate CA bundle — private deployments)
- `_config/playwright/.auth/`, `_config/playwright/chrome-profile/`
- `_config/defaults.ini` (user-local copy of template)
- `contexts/*/repositories/`, `contexts/*/chromadb/`, `contexts/*/cache/`
- `exports/`, `reports/`
- `cache/` (legacy), `repositories/` (legacy)
- `.git-credentials`
- Any file matching `**/.auth/**`, `**/tokens.json`, `**/cookies.json`

## Linked-Project Layout

When this tool is linked into an external project via `<tool> link <path>`, the external project gains:

```
<external-project>/
├── _<tool>/ → (symlink or registry entry)  # Access to the tool from project root
├── CLAUDE.md (augmented)                    # AI instructions with integration section
├── .github/COPILOT_INSTRUCTIONS.md (augmented)
└── <TOOL>_INSTRUCTIONS.md                   # Universal fallback for other AI tools
```

## Rebuilding From Scratch — Minimum Files

To stand up a working (minimal) version, produce in order:
1. `<tool>.py` (CLI dispatcher — see `02-cli/`)
2. `install.py` (bootstrap — see `03-install-setup/`)
3. `scripts/config.py` + `_config/context_defaults.ini`
4. `scripts/context_manager.py` + `contexts/` layout
5. `scripts/cache_manager.py` + `scripts/indexer.py`
6. One provider (e.g., source-control adapter in `scripts/api_skills/` or `scripts/playwright_skills/`)
7. `scripts/rag/` (minimum RAG)
8. `CLAUDE.md` + one `docs/claude/commands.md`

Graph, dashboard, known-contexts, video skills, and the full skill suite are all layered on top of that core.
