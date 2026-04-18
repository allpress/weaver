"""RAG engine: ChromaDB wrapper for per-context collections."""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from weaver import paths
from weaver.rag.embeddings import embed_texts

log = logging.getLogger(__name__)


@dataclass(slots=True)
class RAGHit:
    id: str
    score: float
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class RAGEngine:
    """One engine instance per context. Collections partition by source kind."""

    def __init__(self, context: str, *, embedding_model: str = "all-MiniLM-L6-v2") -> None:
        self._context = context
        self._model = embedding_model
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError as e:
            raise RuntimeError("chromadb required: pip install chromadb") from e

        db_path = paths.context_chromadb_dir(self._context)
        db_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(db_path),
            settings=Settings(anonymized_telemetry=False, allow_reset=True),
        )
        return self._client

    def _collection(self, name: str) -> Any:
        client = self._get_client()
        return client.get_or_create_collection(name=name, metadata={"context": self._context})

    def upsert(self, collection: str, *, items: list[tuple[str, str, dict[str, Any]]]) -> int:
        """Upsert (id, content, metadata) tuples. Embeds locally."""
        if not items:
            return 0
        ids = [i[0] for i in items]
        docs = [i[1] for i in items]
        metas = [_flatten_meta(i[2]) for i in items]
        vectors = embed_texts(docs, model=self._model)
        self._collection(collection).upsert(
            ids=ids, documents=docs, metadatas=metas, embeddings=vectors,
        )
        return len(items)

    def query(self, collection: str, q: str, *, top_k: int = 8,
              where: dict[str, Any] | None = None) -> list[RAGHit]:
        vec = embed_texts([q], model=self._model)[0]
        try:
            result = self._collection(collection).query(
                query_embeddings=[vec], n_results=top_k,
                where=where or None,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("chroma query failed on collection %s: %s", collection, e)
            return []

        hits: list[RAGHit] = []
        for i, doc_id in enumerate(result.get("ids", [[]])[0]):
            hits.append(RAGHit(
                id=doc_id,
                score=float(result["distances"][0][i]) if result.get("distances") else 0.0,
                content=result["documents"][0][i],
                metadata=result["metadatas"][0][i] or {},
            ))
        return hits

    def reset(self, collection: str | None = None) -> None:
        client = self._get_client()
        if collection is None:
            client.reset()
        else:
            try:
                client.delete_collection(collection)
            except Exception:
                pass

    def list_collections(self) -> list[str]:
        client = self._get_client()
        return [c.name for c in client.list_collections()]


def stable_id(*parts: str) -> str:
    h = hashlib.sha1("||".join(parts).encode("utf-8")).hexdigest()
    return h[:16]


def _flatten_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """Chroma requires scalar metadata values. Flatten lists/dicts to JSON strings."""
    import json
    out: dict[str, Any] = {}
    for k, v in meta.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        else:
            out[k] = json.dumps(v, default=str)
    return out


def chunk_text(text: str, *, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    """Simple char-window chunker with overlap. Replace with smarter one later."""
    if len(text) <= chunk_size:
        return [text]
    out: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        out.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return out


def iter_file_pointer(root: Path, *, suffixes: set[str]) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in suffixes]
