"""RAG engine. See extraction/05-modules/core-modules.md."""
from weaver.rag.engine import RAGEngine
from weaver.rag.indexers import index_context
from weaver.rag.embeddings import embed_texts

__all__ = ["RAGEngine", "embed_texts", "index_context"]
