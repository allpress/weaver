---
description: Clone a GitLab group into an weaver context, build RAG + code graph
argument-hint: <context-name> <gitlab-url> <group>
---

Run the full ingest pipeline for a GitLab group:

```bash
weaver clone gitlab \
  --context "$1" \
  --base-url "$2" \
  --group "$3"
```

When this finishes:
- Repos are under `contexts/$1/repositories/`
- Docs are indexed in ChromaDB at `contexts/$1/chromadb/`
- Code graph snapshot at `contexts/$1/graph/snapshots/latest.json`

If auth fails, run `weaver secret set gitlab token --context $1` first.
