"""Retrieval evaluation (F4): Recall@K, MRR over answerable cases; refusal rate over refusal cases."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from ..config import get_settings
from ..db import SessionLocal
from ..errors import BadRequest
from ..models import Document, EvalRun
from . import document_service
from .retriever import retrieve


def cases_path() -> Path:
    return get_settings().evals_dir / "cases.json"


def load_cases() -> dict:
    path = cases_path()
    if not path.exists():
        raise BadRequest("评测集 evals/cases.json 不存在", detail=str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def _group_hit_rank(group: dict, candidates: list) -> tuple[int, str | None]:
    doc_key = group.get("document", "")
    keywords = group.get("keywords", [])
    for rank, cand in enumerate(candidates, start=1):
        if doc_key and doc_key not in cand.document_name:
            continue
        if all(kw in cand.content for kw in keywords):
            return rank, cand.chunk_id
    return 0, None


async def run_eval(chunk_size: int | None, chunk_overlap: int | None, use_hybrid: bool | None, use_rerank: bool | None, k: int | None) -> EvalRun:
    settings = get_settings()
    k = k or settings.top_k
    use_hybrid = settings.use_hybrid if use_hybrid is None else use_hybrid
    use_rerank = settings.rerank_enabled if use_rerank is None else use_rerank

    db = SessionLocal()
    try:
        ready = db.execute(select(Document).where(Document.status == "ready")).scalars().all()
        if not ready:
            raise BadRequest("没有就绪的文档，请先上传文档")
        current_size = ready[0].chunk_size
        current_overlap = ready[0].chunk_overlap
        needs_reindex = any(
            (chunk_size is not None and d.chunk_size != chunk_size)
            or (chunk_overlap is not None and d.chunk_overlap != chunk_overlap)
            for d in ready
        )
    finally:
        db.close()

    target_size = chunk_size if chunk_size is not None else current_size
    target_overlap = chunk_overlap if chunk_overlap is not None else current_overlap
    if target_overlap >= target_size:
        raise BadRequest("chunk_overlap 必须小于 chunk_size")
    if needs_reindex:
        await asyncio.to_thread(document_service.reindex_all_ready, target_size, target_overlap)

    data = load_cases()
    cases = data.get("cases", [])
    detail: list[dict] = []
    answerable_total = 0
    answerable_hit = 0
    reciprocal_sum = 0.0
    refusal_total = 0
    refusal_hit = 0

    for idx, case in enumerate(cases):
        if use_rerank and idx > 0 and settings.rerank_eval_interval > 0:
            await asyncio.sleep(settings.rerank_eval_interval)
        result = await retrieve(case["question"], use_hybrid=use_hybrid, use_rerank=use_rerank, top_k=k)
        if case.get("type") == "refusal":
            refusal_total += 1
            hit = result.refused
            refusal_hit += int(hit)
            detail.append(
                {
                    "id": case["id"],
                    "type": "refusal",
                    "question": case["question"],
                    "hit": hit,
                    "rank": 0,
                    "matched_chunk_ids": [],
                    "gate_score": round(result.gate_score, 4),
                    "answer_points": case.get("answer_points", []),
                }
            )
            continue

        answerable_total += 1
        # a refused answerable case has no Top-K, so it counts as a miss
        candidates = result.candidates
        ranks: list[int] = []
        matched: list[str] = []
        for group in case.get("expects", []):
            rank, cid = _group_hit_rank(group, candidates)
            ranks.append(rank)
            if cid:
                matched.append(cid)
        hit = bool(ranks) and all(r > 0 for r in ranks)
        rank = max(ranks) if hit else 0
        if hit:
            answerable_hit += 1
            reciprocal_sum += 1.0 / rank
        detail.append(
            {
                "id": case["id"],
                "type": "answerable",
                "question": case["question"],
                "hit": hit,
                "rank": rank,
                "matched_chunk_ids": matched,
                "gate_score": round(result.gate_score, 4),
                "answer_points": case.get("answer_points", []),
            }
        )

    run = EvalRun(
        config={
            "chunk_size": target_size,
            "chunk_overlap": target_overlap,
            "use_hybrid": use_hybrid,
            "use_rerank": use_rerank,
            "k": k,
        },
        recall_at_k=round(answerable_hit / answerable_total, 4) if answerable_total else 0.0,
        mrr=round(reciprocal_sum / answerable_total, 4) if answerable_total else 0.0,
        refusal_rate=round(refusal_hit / refusal_total, 4) if refusal_total else 0.0,
        case_count=len(cases),
        detail=detail,
    )
    db = SessionLocal()
    try:
        db.add(run)
        db.commit()
        db.refresh(run)
    finally:
        db.close()
    return run
