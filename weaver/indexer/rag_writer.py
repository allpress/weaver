"""Upsert condensed article into the per-context ChromaDB collection.

RAG deps are optional. Importing this module is cheap; the heavy imports
(sentence-transformers, chromadb) fire only when `upsert_extracted` runs.
"""
from __future__ import annotations

import logging
from typing import Any

from weaver.indexer.models import ArticleFacts

log = logging.getLogger(__name__)

_COLLECTION = "aggregated_articles"


class RAGUnavailable(RuntimeError):
    pass


def upsert_extracted(context: str, facts: ArticleFacts, *,
                     embedding_model: str = "all-MiniLM-L6-v2") -> int:
    """Write one article's condensed content to the per-context Chroma collection.

    Returns the number of records written (1 if success).
    """
    try:
        from weaver.rag.engine import RAGEngine, stable_id
    except ImportError as e:
        raise RAGUnavailable(
            "RAG deps missing. Install: pip install -e 'weaver[rag]'"
        ) from e

    engine = RAGEngine(context, embedding_model=embedding_model)
    doc_id = stable_id(context, facts.source, facts.sha)

    # Chroma requires scalar metadata values; flatten lists to delimited strings.
    metadata: dict[str, Any] = {
        "sha": facts.sha,
        "source": facts.source,
        "url": facts.url,
        "title": facts.title,
        "author": facts.author or "",
        "published_at": facts.published_at.isoformat() if facts.published_at else "",
        "indexed_at": facts.indexed_at.isoformat(),
        "model": facts.model or "",
        "key_concepts": ", ".join(facts.extracted.key_concepts),
        "people": ", ".join(p.name for p in facts.extracted.people),
        "projects": ", ".join(p.name for p in facts.extracted.projects),
        "technologies": ", ".join(facts.extracted.technologies),
    }

    # The searchable document is the condensation + concept/people/project names
    # so queries can hit either prose or entity terms.
    doc_text = "\n\n".join([
        f"Title: {facts.title}",
        f"Source: {facts.source}",
        f"Summary: {facts.extracted.summary}",
        f"Concepts: {', '.join(facts.extracted.key_concepts)}",
        f"People: {', '.join(p.name for p in facts.extracted.people)}",
        f"Projects: {', '.join(p.name for p in facts.extracted.projects)}",
        f"Technologies: {', '.join(facts.extracted.technologies)}",
    ])

    return engine.upsert(_COLLECTION, items=[(doc_id, doc_text, metadata)])


def rag_available() -> bool:
    try:
        import chromadb  # noqa: F401
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return True
