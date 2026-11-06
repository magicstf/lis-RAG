"""Token / call accounting (N3)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from ..db import SessionLocal, session_scope
from ..models import UsageLog

log = logging.getLogger("rag.usage")


def record(kind: str, prompt_tokens: int, completion_tokens: int, calls: int = 1) -> None:
    try:
        with session_scope() as db:
            for _ in range(max(1, calls)):
                db.add(UsageLog(kind=kind, prompt_tokens=prompt_tokens or 0, completion_tokens=completion_tokens or 0))
                prompt_tokens, completion_tokens = 0, 0
    except Exception as exc:  # accounting must never break the main flow
        log.warning("usage record failed: %s", exc)


def daily(days: int = 7) -> list[dict]:
    today = datetime.now(timezone.utc).date()
    start_day = today - timedelta(days=days - 1)
    start_dt = datetime(start_day.year, start_day.month, start_day.day, tzinfo=timezone.utc)
    buckets: dict[str, dict] = {}
    for i in range(days):
        day = start_day + timedelta(days=i)
        buckets[day.isoformat()] = {
            "date": day.isoformat(),
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "llm_calls": 0,
            "embedding_calls": 0,
        }
    db = SessionLocal()
    try:
        rows = db.execute(select(UsageLog).where(UsageLog.created_at >= start_dt)).scalars().all()
    finally:
        db.close()
    for row in rows:
        created = row.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        key = created.astimezone(timezone.utc).date().isoformat()
        bucket = buckets.get(key)
        if not bucket:
            continue
        if row.kind == "llm":
            bucket["llm_calls"] += 1
            bucket["prompt_tokens"] += row.prompt_tokens
            bucket["completion_tokens"] += row.completion_tokens
        elif row.kind == "embedding":
            bucket["embedding_calls"] += 1
    return list(buckets.values())
