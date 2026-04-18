---
description: Rebuild or inspect the code graph for an weaver context
argument-hint: <context-name> [build|stats|export]
---

Graph operations:

```bash
# Default: show stats
weaver graph stats --context "$1"

# Rebuild from scratch
weaver graph build --context "$1"

# Export to GraphML for visualization
weaver graph export --context "$1" --format graphml --out exports/$1.graphml
```
