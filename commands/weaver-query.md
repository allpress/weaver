---
description: Query the RAG+graph bridge for an weaver context
argument-hint: <context-name> <question>
---

Walk the bridged index for context `$1` with question `$ARGUMENTS_AFTER_1`:

```bash
weaver rag query --context "$1" --bridge $ARGUMENTS_AFTER_1
```

Returns top matches reweighted by graph centrality. Use `--no-bridge` for raw RAG-only.
