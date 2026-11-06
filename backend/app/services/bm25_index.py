"""In-memory BM25 index over all ready chunks (F5-1)."""
from __future__ import annotations

import logging
import threading

from sqlalchemy import select

from ..db import SessionLocal
from ..models import Chunk, Document

log = logging.getLogger("rag.bm25")

_lock = threading.Lock()
_bm25 = None
_chunk_ids: list[str] = []


def tokenize(text: str) -> list[str]:
    import jieba

    return [tok for tok in jieba.cut_for_search(text) if tok.strip()]


def rebuild() -> int:
    global _bm25, _chunk_ids
    db = SessionLocal()
    try:
        rows = db.execute(
            select(Chunk.id, Chunk.content).join(Document, Document.id == Chunk.document_id).where(Document.status == "ready")
        ).all()
    finally:
        db.close()
    ids = [r[0] for r in rows]
    corpus = [tokenize(r[1]) for r in rows]
    with _lock:
        if corpus:
            from rank_bm25 import BM25Okapi

            _bm25 = BM25Okapi(corpus)
        else:
            _bm25 = None
        _chunk_ids = ids
    log.info("bm25 index rebuilt with %d chunks", len(ids))
    return len(ids)


def search(query: str, k: int) -> list[tuple[str, float]]:
    with _lock:
        bm25, ids = _bm25, list(_chunk_ids)
    if bm25 is None or not ids:
        return []
    tokens = tokenize(query)
    if not tokens:
        return []
    scores = bm25.get_scores(tokens)
    ranked = sorted(range(len(ids)), key=lambda i: scores[i], reverse=True)
    out: list[tuple[str, float]] = []
    for i in ranked[:k]:
        if scores[i] <= 0:
            break
        out.append((ids[i], float(scores[i])))
    return out
