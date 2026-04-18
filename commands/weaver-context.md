---
description: Manage weaver contexts (isolated knowledge domains)
argument-hint: [list|create|show|rm] [<name>]
---

Context lifecycle. Each context is its own isolated knowledge domain — separate repos, RAG index, and graph.

```bash
weaver context list
weaver context create "$1"
weaver context show "$1"
weaver context rm "$1" --force
```
