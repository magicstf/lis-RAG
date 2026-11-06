from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import ok
from ..models import EvalRun
from ..schemas import EvalRunRequest
from ..services import evaluator

router = APIRouter(prefix="/evals", tags=["evals"])


@router.get("/cases")
def get_cases():
    return ok(evaluator.load_cases())


@router.post("/run")
async def run_eval(body: EvalRunRequest | None = None):
    body = body or EvalRunRequest()
    run = await evaluator.run_eval(body.chunk_size, body.chunk_overlap, body.use_hybrid, body.use_rerank, body.k)
    return ok(run.to_dict())


@router.get("/runs")
def list_runs(db: Session = Depends(get_db)):
    rows = db.execute(select(EvalRun).order_by(EvalRun.created_at.desc())).scalars().all()
    return ok([r.to_dict() for r in rows])
