"""Cohere rerank (F5-2)."""
from __future__ import annotations

import httpx

from ..config import get_settings
from ..errors import UpstreamError
from .retry import FatalUpstream, RetryableUpstream, classify_http_status, with_retry

RERANK_TIMEOUT = 30.0


async def rerank(query: str, documents: list[str], top_n: int) -> list[tuple[int, float]]:
    """Return [(index_in_documents, relevance_score)] sorted by score desc."""
    settings = get_settings()
    if not documents:
        return []
    if not settings.cohere_api_key:
        raise UpstreamError("COHERE_API_KEY 未配置，无法启用 rerank", detail="missing COHERE_API_KEY")

    payload = {
        "model": settings.rerank_model,
        "query": query,
        "documents": documents,
        "top_n": min(top_n, len(documents)),
    }
    headers = {"Authorization": f"Bearer {settings.cohere_api_key}", "Content-Type": "application/json"}

    async def _call():
        async with httpx.AsyncClient(timeout=httpx.Timeout(RERANK_TIMEOUT, connect=10.0)) as client:
            resp = await client.post(settings.rerank_base_url, json=payload, headers=headers)
        cls = classify_http_status(resp.status_code)
        if cls is RetryableUpstream:
            raise RetryableUpstream(f"rerank http {resp.status_code}: {resp.text[:200]}")
        if cls is FatalUpstream:
            raise FatalUpstream(f"rerank http {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        results = data.get("results", [])
        out = [(int(r["index"]), float(r["relevance_score"])) for r in results]
        out.sort(key=lambda x: x[1], reverse=True)
        return out

    # Cohere trial keys allow 10 calls/minute, so rate-limit retries wait longer than the LLM default
    # (about 20s then 40s, enough for the per-minute window to reset).
    return await with_retry("rerank", _call, friendly_error="重排服务暂时不可用", base_delay=20.0)
