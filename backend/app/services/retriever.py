"""Retrieval pipeline: vector + BM25 + RRF + optional rerank + refusal gate (PRD 5.5)."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from ..config import get_settings
from . import bm25_index, embedding, reranker, vector_store


@dataclass
class Candidate:
    chunk_id: str
    document_id: str
    document_name: str
    content: str
    page_no: int | None
    section: str
    cosine: float = 0.0
    rrf: float = 0.0
    rerank_score: float | None = None

    @property
    def score(self) -> float:
        return self.rerank_score if self.rerank_score is not None else self.cosine

    def to_citation(self, index: int) -> dict:
        return {
            "index": index,
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "document_name": self.document_name,
            "content": self.content,
            "page_no": self.page_no,
            "section": self.section or "",
            "score": round(self.score, 4),
        }


@dataclass
class RetrievalResult:
    candidates: list[Candidate] = field(default_factory=list)   # final Top-K (empty when refused)
    refused: bool = False
    gate_score: float = 0.0
    gate_kind: str = "vector"  # vector | rerank | empty
    use_hybrid: bool = False
    use_rerank: bool = False

    def citations(self) -> list[dict]:
        return [c.to_citation(i + 1) for i, c in enumerate(self.candidates)]


def _from_hit(hit: vector_store.VectorHit) -> Candidate:
    meta = hit.metadata or {}
    page = meta.get("page_no")
    return Candidate(
        chunk_id=hit.chunk_id,
        document_id=str(meta.get("document_id", "")),
        document_name=str(meta.get("document_name", "")),
        content=hit.content,
        page_no=int(page) if isinstance(page, (int, float)) and page is not None else None,
        section=str(meta.get("section", "") or ""),
        cosine=hit.cosine,
    )


def _dot(a: list[float], b: list[float]) -> float:
    return float(sum(x * y for x, y in zip(a, b)))


async def retrieve(
    query: str,
    *,
    use_hybrid: bool | None = None,
    use_rerank: bool | None = None,
    top_k: int | None = None,
) -> RetrievalResult:
    settings = get_settings()
    use_hybrid = settings.use_hybrid if use_hybrid is None else use_hybrid
    use_rerank = settings.rerank_enabled if use_rerank is None else use_rerank
    top_k = top_k or settings.top_k
    recall_k = settings.recall_k

    result = RetrievalResult(use_hybrid=use_hybrid, use_rerank=use_rerank)

    query_vec = await asyncio.to_thread(embedding.embed_query, query)
    vector_hits = await asyncio.to_thread(vector_store.query, query_vec, recall_k)
    candidates: dict[str, Candidate] = {h.chunk_id: _from_hit(h) for h in vector_hits}

    if use_hybrid:
        bm25_hits = await asyncio.to_thread(bm25_index.search, query, recall_k)
        missing = [cid for cid, _ in bm25_hits if cid not in candidates]
        if missing:
            fetched = await asyncio.to_thread(vector_store.get_by_ids, missing, True)
            for cid, hit in fetched.items():
                cand = _from_hit(hit)
                cand.cosine = max(0.0, min(1.0, _dot(query_vec, hit.embedding))) if hit.embedding else 0.0
                candidates[cid] = cand
        k = settings.rrf_k
        for rank, hit in enumerate(vector_hits, start=1):
            candidates[hit.chunk_id].rrf += 1.0 / (k + rank)
        for rank, (cid, _) in enumerate(bm25_hits, start=1):
            if cid in candidates:
                candidates[cid].rrf += 1.0 / (k + rank)
        ordered = sorted(candidates.values(), key=lambda c: (c.rrf, c.cosine), reverse=True)
    else:
        ordered = sorted(candidates.values(), key=lambda c: c.cosine, reverse=True)

    if not ordered:
        result.refused = True
        result.gate_kind = "empty"
        return result

    if use_rerank:
        pool = ordered[:20]
        scores = await reranker.rerank(query, [c.content for c in pool], top_k)
        reranked: list[Candidate] = []
        for idx, score in scores:
            cand = pool[idx]
            cand.rerank_score = score
            reranked.append(cand)
        final = reranked[:top_k]
        result.gate_kind = "rerank"
        result.gate_score = final[0].rerank_score if final else 0.0
        if not final or result.gate_score < settings.rerank_threshold:
            result.refused = True
            return result
        result.candidates = final
        return result

    final = ordered[:top_k]
    result.gate_kind = "vector"
    result.gate_score = max(c.cosine for c in ordered)
    if result.gate_score < settings.vector_threshold:
        result.refused = True
        return result
    result.candidates = final
    return result
