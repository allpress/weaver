# Specification

> What Weaver will do. This is the living spec — it evolves as the project takes shape.

## Problem

AI agents need context to be useful. Today, context is:
- **Fragmented** — spread across repos, docs, conversations, issue trackers
- **One-directional** — agents consume context but don't contribute back
- **Static** — context is a snapshot, not a living graph
- **Unconnected** — related pieces of context don't know about each other

## Solution

Weaver is a bidirectional context-weaving engine. It:

1. **Ingests** context from multiple sources into a unified graph
2. **Weaves** relationships between context nodes (semantic, structural, temporal)
3. **Serves** relevant context to agents based on their current task
4. **Absorbs** what agents produce back into the graph

The graph gets richer with every interaction.

## Core Concepts

### Context Node
A discrete unit of context: a file, a function, a conversation message, a document section, an issue, a commit.

```python
@dataclass(slots=True)
class ContextNode:
    id: str
    source: str                         # where it came from
    content: str                        # the actual content
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
```

### Edge
A relationship between two context nodes.

```python
@dataclass(slots=True, frozen=True)
class Edge:
    from_id: str
    to_id: str
    type: EdgeType                      # semantic | structural | temporal | reference
    weight: float                       # 0.0–1.0 strength
    metadata: dict[str, Any] = field(default_factory=dict)
```

### Weave
A subgraph of relevant context assembled for a specific query or task.

```python
@dataclass(slots=True)
class Weave:
    query: str
    nodes: list[ContextNode]
    edges: list[Edge]
    score: float                        # relevance score
```

## Ingestion Sources (Planned)

| Source | Priority | Status |
|--------|----------|--------|
| Git repositories (files + history) | P0 | Planned |
| Markdown / text documents | P0 | Planned |
| JIRA / Linear issues | P1 | Planned |
| Confluence / Notion pages | P1 | Planned |
| Slack / Discord messages | P2 | Planned |
| API schemas (OpenAPI) | P2 | Planned |

## Weaving Strategies

- **Semantic** — Cosine similarity between embeddings
- **Structural** — AST imports, function calls, file references
- **Temporal** — Changed together, discussed together, created near each other
- **Reference** — Explicit links (URLs, issue numbers, @mentions)

## API Surface (Draft)

```python
# Ingest a new source
weaver.ingest(source: SourceConfig) -> IngestResult

# Query for relevant context
weaver.query(q: str, options: QueryOptions | None = None) -> Weave

# Feed agent output back into the graph
weaver.sync(nodes: list[ContextNode]) -> SyncResult

# Get the graph state
weaver.graph() -> ContextGraph
```

## First-Class Families

Weaver has two peer extension families. Both are plugin-based and core knows nothing about specific implementations.

- **Providers** — fetch raw records from external systems (JIRA, GitLab, Confluence, Splunk, ServiceNow, arbitrary web via Wayfinder). See [extraction/04-providers/](../extraction/04-providers/).
- **Parsers** — turn raw bytes/strings into structured `ContextNode`s (HTML, PDF, DOCX, Markdown, OpenAPI, source code, etc.). See [extraction/04-providers/parsers.md](../extraction/04-providers/parsers.md).

A typical ingest: provider fetches → parser normalizes → weaver embeds + edges → graph absorbs.

## Non-Goals (for now)

- Weaver is not a vector database — it uses one under the hood
- Weaver is not an agent framework — it provides context to agents
- Weaver is not a search engine — search is one interface to the graph
