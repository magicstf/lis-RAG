"""Chroma persistent collection wrapper."""
from __future__ import annotations

import threading
from dataclasses import dataclass

from ..config import get_settings

COLLECTION = "kb_chunks"

_client = None
_collection = None
_lock = threading.Lock()


@dataclass
class VectorHit:
    chunk_id: str
    distance: float
    content: str
    metadata: dict
    embedding: list[float] | None = None

    @property
    def cosine(self) -> float:
        value = 1.0 - float(self.distance)
        return max(0.0, min(1.0, value))


def get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection
    with _lock:
        if _collection is None:
            import chromadb

            settings = get_settings()
            settings.chroma_path.mkdir(parents=True, exist_ok=True)
            _client = chromadb.PersistentClient(path=str(settings.chroma_path))
            _collection = _client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
    return _collection


def add(ids: list[str], embeddings: list[list[float]], documents: list[str], metadatas: list[dict]) -> None:
    if not ids:
        return
    collection = get_collection()
    for i in range(0, len(ids), 256):
        collection.add(
            ids=ids[i : i + 256],
            embeddings=embeddings[i : i + 256],
            documents=documents[i : i + 256],
            metadatas=metadatas[i : i + 256],
        )


def delete_document(document_id: str) -> None:
    collection = get_collection()
    try:
        collection.delete(where={"document_id": document_id})
    except Exception:
        pass


def delete_ids(ids: list[str]) -> None:
    if not ids:
        return
    get_collection().delete(ids=ids)


def count() -> int:
    return get_collection().count()


def query(embedding: list[float], n_results: int) -> list[VectorHit]:
    collection = get_collection()
    total = collection.count()
    if total == 0:
        return []
    res = collection.query(
        query_embeddings=[embedding],
        n_results=min(n_results, total),
        include=["documents", "metadatas", "distances"],
    )
    hits: list[VectorHit] = []
    ids = res.get("ids", [[]])[0]
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]
    for cid, doc, meta, dist in zip(ids, docs, metas, dists):
        hits.append(VectorHit(chunk_id=cid, distance=dist, content=doc or "", metadata=meta or {}))
    return hits


def get_by_ids(ids: list[str], with_embeddings: bool = False) -> dict[str, VectorHit]:
    if not ids:
        return {}
    include = ["documents", "metadatas"] + (["embeddings"] if with_embeddings else [])
    res = get_collection().get(ids=ids, include=include)
    out: dict[str, VectorHit] = {}
    embeddings = res.get("embeddings")
    for idx, cid in enumerate(res.get("ids", [])):
        emb = None
        if embeddings is not None and len(embeddings) > idx:
            emb = [float(x) for x in embeddings[idx]]
        out[cid] = VectorHit(
            chunk_id=cid,
            distance=1.0,
            content=(res.get("documents") or [""])[idx] or "",
            metadata=(res.get("metadatas") or [{}])[idx] or {},
            embedding=emb,
        )
    return out
