"""OpenAI-compatible chat client with timeouts, retries and usage accounting."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx

from ..config import get_settings
from ..errors import UpstreamError
from . import usage
from .retry import FatalUpstream, RetryableUpstream, with_retry

log = logging.getLogger("rag.llm")

CONNECT_TIMEOUT = 10.0
GENERATE_TIMEOUT = 120.0
REWRITE_TIMEOUT = 15.0

_client = None
# Parameters the upstream model has rejected ("Parameter 'x' is not supported"); dropped on later calls.
_unsupported_params: set[str] = set()
_PARAM_RE = re.compile(r"[Pp]arameter '?(\w+)'?.*not supported")


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


def _get_client():
    global _client
    if _client is None:
        from openai import AsyncOpenAI

        settings = get_settings()
        if not settings.llm_api_key:
            raise UpstreamError("LLM_API_KEY 未配置，请在 backend/.env 中填写", detail="missing LLM_API_KEY")
        _client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            max_retries=0,
            timeout=httpx.Timeout(GENERATE_TIMEOUT, connect=CONNECT_TIMEOUT),
        )
    return _client


def _translate(exc: Exception) -> Exception:
    from openai import (
        APIConnectionError,
        APIStatusError,
        APITimeoutError,
        AuthenticationError,
        BadRequestError,
        PermissionDeniedError,
        RateLimitError,
    )

    if isinstance(exc, (AuthenticationError, PermissionDeniedError, BadRequestError)):
        return FatalUpstream(str(exc))
    if isinstance(exc, RateLimitError):
        return RetryableUpstream(str(exc))
    if isinstance(exc, APITimeoutError):
        return httpx.ReadTimeout(str(exc))
    if isinstance(exc, APIConnectionError):
        return httpx.ConnectError(str(exc))
    if isinstance(exc, APIStatusError):
        return RetryableUpstream(str(exc)) if exc.status_code >= 500 else FatalUpstream(str(exc))
    return exc


def _rejected_param(exc: Exception) -> str | None:
    text = str(exc)
    if "enable_thinking" in text:
        return "enable_thinking"
    match = _PARAM_RE.search(text)
    return match.group(1) if match else None


def _build_kwargs(messages: list[dict], temperature: float, max_tokens: int, timeout: float, stream: bool) -> dict[str, Any]:
    settings = get_settings()
    kwargs: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timeout": httpx.Timeout(timeout, connect=CONNECT_TIMEOUT),
    }
    extra: dict[str, Any] = {"enable_thinking": False}
    if stream:
        kwargs["stream"] = True
        kwargs["stream_options"] = {"include_usage": True}
    for name in _unsupported_params:
        kwargs.pop(name, None)
        extra.pop(name, None)
    if extra:
        kwargs["extra_body"] = extra
    return kwargs


async def _create(messages: list[dict], temperature: float, max_tokens: int, timeout: float, stream: bool):
    """Call chat.completions, dropping parameters the upstream rejects (at most a few rounds)."""
    client = _get_client()
    for _ in range(4):
        kwargs = _build_kwargs(messages, temperature, max_tokens, timeout, stream)
        try:
            return await client.chat.completions.create(**kwargs)
        except Exception as exc:
            param = _rejected_param(exc)
            if param and param not in _unsupported_params:
                log.warning("upstream rejected parameter %s, retrying without it", param)
                _unsupported_params.add(param)
                continue
            raise _translate(exc) from exc
    raise FatalUpstream("upstream kept rejecting request parameters")


async def complete(
    messages: list[dict],
    *,
    temperature: float = 0.2,
    max_tokens: int = 1024,
    timeout: float = GENERATE_TIMEOUT,
) -> tuple[str, Usage]:
    async def _call():
        resp = await _create(messages, temperature, max_tokens, timeout, stream=False)
        text = (resp.choices[0].message.content or "") if resp.choices else ""
        u = Usage()
        if resp.usage:
            u = Usage(resp.usage.prompt_tokens or 0, resp.usage.completion_tokens or 0)
        usage.record("llm", u.prompt_tokens, u.completion_tokens)
        return text, u

    return await with_retry("llm.complete", _call)


async def rewrite_query(messages: list[dict]) -> tuple[str, Usage]:
    return await complete(messages, temperature=0.0, max_tokens=256, timeout=REWRITE_TIMEOUT)


class StreamResult:
    """Collects usage while deltas are consumed."""

    def __init__(self) -> None:
        self.usage = Usage()


async def stream(messages: list[dict], result: StreamResult, *, temperature: float = 0.2, max_tokens: int = 1024) -> AsyncIterator[str]:
    """Yield content deltas. Establishing the stream is retried; mid-stream errors propagate."""

    async def _open():
        return await _create(messages, temperature, max_tokens, GENERATE_TIMEOUT, stream=True)

    response = await with_retry("llm.stream", _open)
    try:
        async for chunk in response:
            if getattr(chunk, "usage", None):
                result.usage = Usage(chunk.usage.prompt_tokens or 0, chunk.usage.completion_tokens or 0)
            if chunk.choices:
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    yield content
    except Exception as exc:
        raise UpstreamError("模型输出中断，请重试", detail=f"{type(exc).__name__}: {exc}") from exc
    finally:
        try:
            await response.close()
        except Exception:
            pass
        usage.record("llm", result.usage.prompt_tokens, result.usage.completion_tokens)
