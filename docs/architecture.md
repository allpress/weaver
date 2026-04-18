# Architecture

> How Weaver is structured internally.

## Overview

```
┌─────────────────────────────────────────┐
│              Agent / Client             │
└──────────────────┬──────────────────────┘
                   │
┌──────────────────▼──────────────────────┐
│                 API                      │
│         (query, ingest, sync)           │
└──────┬───────────┬───────────┬──────────┘
       │           │           │
┌──────▼──┐  ┌─────▼─────┐  ┌─▼────────┐
│ Ingest  │  │  Weaver   │  │  Sync    │
│ Layer   │  │  Engine   │  │ Protocol │
└──────┬──┘  └─────┬─────┘  └─┬────────┘
       │           │           │
┌──────▼───────────▼───────────▼──────────┐
│            Context Graph                 │
│     (nodes, edges, embeddings)          │
└─────────────────────────────────────────┘
```

## Layers

### Ingestion Layer
Connectors that pull context from external sources: git repos, documents, APIs, conversations, issue trackers.

### Weaver Engine
The core. Maps relationships between context nodes — dependencies, references, semantic similarity, temporal proximity. This is where raw context becomes a connected graph.

### Sync Protocol
Bidirectional: agents consume context and produce new context. The sync protocol handles the feedback loop — what agents learn gets woven back in.

### Context Graph
The underlying data structure. Nodes are context fragments. Edges are relationships. Embeddings enable semantic search across the graph.

### API
The public surface. Query for relevant context, ingest new sources, sync agent state.

## Design Principles

1. **Bidirectional by default** — Context is not read-only. Agents write back.
2. **Lazy weaving** — Relationships are discovered on demand, not pre-computed.
3. **Source-agnostic** — A git commit, a Slack message, and a PDF page are all context nodes.
4. **Plugin-first** — Ingestion connectors and weaving strategies are pluggable.
