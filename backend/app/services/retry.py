"""Shared timeout / retry policy for every upstream call (N1)."""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Awaitable, Callable, TypeVar

import httpx

from ..errors import AppError, UpstreamError, UpstreamTimeout

log = logging.getLogger("rag.retry")

T = TypeVar("T")

MAX_RETRIES = 2
BASE_DELAY = 0.8


class RetryableUpstream(Exception):
    """Transient upstream failure (network / 429 / 5xx)."""


class FatalUpstream(Exception):
    """Configuration or request error that retrying will not fix (401/403/400...)."""


def classify_http_status(status: int) -> type[Exception] | None:
    if status == 429 or status >= 500:
        return RetryableUpstream
    if status >= 400:
        return FatalUpstream
    return None


async def with_retry(
    name: str,
    factory: Callable[[], Awaitable[T]],
    *,
    retries: int = MAX_RETRIES,
    friendly_error: str = "模型暂时不可用，请稍后重试",
    base_delay: float = BASE_DELAY,
) -> T:
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return await factory()
        except AppError:
            raise
        except FatalUpstream as exc:
            raise UpstreamError(f"{friendly_error}（配置或请求被上游拒绝）", detail=str(exc)) from exc
        except (httpx.TimeoutException, asyncio.TimeoutError) as exc:
            last_exc = exc
            kind = "timeout"
        except (RetryableUpstream, httpx.TransportError) as exc:
            last_exc = exc
            kind = "retryable"
        except Exception as exc:  # unknown SDK error: inspect for status code
            status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
            cls = classify_http_status(int(status)) if status else None
            if cls is FatalUpstream:
                raise UpstreamError(f"{friendly_error}（配置或请求被上游拒绝）", detail=str(exc)) from exc
            if cls is RetryableUpstream or "timeout" in type(exc).__name__.lower() or "connection" in type(exc).__name__.lower():
                last_exc = exc
                kind = "timeout" if "timeout" in type(exc).__name__.lower() else "retryable"
            else:
                raise UpstreamError(friendly_error, detail=f"{type(exc).__name__}: {exc}") from exc
        if attempt < retries:
            delay = base_delay * (2**attempt) + random.uniform(0, 0.3)
            log.warning("%s failed (%s), retry %d/%d in %.1fs: %s", name, kind, attempt + 1, retries, delay, last_exc)
            await asyncio.sleep(delay)
    if isinstance(last_exc, (httpx.TimeoutException, asyncio.TimeoutError)) or "timeout" in type(last_exc).__name__.lower():
        raise UpstreamTimeout(f"{friendly_error}（上游超时）", detail=str(last_exc)) from last_exc
    raise UpstreamError(friendly_error, detail=str(last_exc)) from last_exc
