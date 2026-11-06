from __future__ import annotations

from fastapi import APIRouter

from ..errors import ok
from ..services import usage

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/daily")
def usage_daily():
    return ok({"days": usage.daily(7)})
