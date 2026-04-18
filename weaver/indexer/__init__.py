"""Indexer — walk the aggregator cache, condense with a local LLM, upsert to RAG + graph."""
from weaver.indexer.condenser import condense_article
from weaver.indexer.llm_client import (
    LLMClient,
    OllamaClient,
    OllamaConnectionError,
    OllamaError,
    OllamaValidationError,
)
from weaver.indexer.models import ExtractedArticle, Person, Project
from weaver.indexer.runner import IndexerResult, run_index
from weaver.indexer.state import IndexerState, load_state, save_state

__all__ = [
    "ExtractedArticle", "IndexerResult", "IndexerState",
    "LLMClient", "OllamaClient",
    "OllamaConnectionError", "OllamaError", "OllamaValidationError",
    "Person", "Project",
    "condense_article", "load_state", "run_index", "save_state",
]
