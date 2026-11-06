"""Chat orchestration: history, query rewrite, retrieval, generation, persistence, SSE."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import AsyncIterator

from sqlalchemy import select

from ..config import get_settings
from ..db import SessionLocal
from ..errors import AppError, BadRequest, NotFound
from ..models import Conversation, Message, new_id, utcnow
from . import llm
from .prompts import REFUSAL_TEXT, build_generation_messages, build_rewrite_messages
from .retriever import RetrievalResult, retrieve

log = logging.getLogger("rag.chat")

# message_id -> cancel event (F2-7)
_cancel_flags: dict[str, asyncio.Event] = {}


def request_stop(message_id: str) -> bool:
    flag = _cancel_flags.get(message_id)
    if flag is None:
        return False
    flag.set()
    return True


@dataclass
class ChatContext:
    conversation_id: str
    question: str
    rewritten: str
    history: list[dict]
    assistant_message_id: str
    rewrite_usage: llm.Usage = field(default_factory=llm.Usage)


def validate_question(question: str) -> str:
    settings = get_settings()
    q = (question or "").strip()
    if not q:
        raise BadRequest("问题不能为空")
    if len(q) > settings.max_question_chars:
        raise BadRequest(f"问题长度不能超过 {settings.max_question_chars} 个字符")
    return q


def _history(db, conversation_id: str, rounds: int, before_message_id: str | None = None) -> list[dict]:
    rows = db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    ).scalars().all()
    if before_message_id:
        cut = next((i for i, m in enumerate(rows) if m.id == before_message_id), None)
        if cut is not None:
            rows = rows[:cut]
    # keep only completed/stopped assistant answers and their user turns; last `rounds` pairs
    pairs: list[dict] = [{"role": m.role, "content": m.content} for m in rows if m.content]
    return pairs[-(rounds * 2) :] if rounds > 0 else []


def start_turn(db, conversation_id: str, question: str) -> ChatContext:
    conv = db.get(Conversation, conversation_id)
    if conv is None:
        raise NotFound("会话不存在")
    question = validate_question(question)
    settings = get_settings()
    history = _history(db, conversation_id, settings.history_rounds)

    user_msg = Message(conversation_id=conversation_id, role="user", content=question, citations=[], status="completed")
    db.add(user_msg)
    has_user = any(m["role"] == "user" for m in history)
    if not has_user:
        conv.title = question[:20]
    conv.updated_at = utcnow()
    db.commit()

    return ChatContext(
        conversation_id=conversation_id,
        question=question,
        rewritten=question,
        history=history,
        assistant_message_id=new_id(),
    )


def start_regenerate(db, conversation_id: str, message_id: str) -> ChatContext:
    conv = db.get(Conversation, conversation_id)
    if conv is None:
        raise NotFound("会话不存在")
    target = db.get(Message, message_id)
    if target is None or target.conversation_id != conversation_id:
        raise NotFound("消息不存在")
    if target.role != "assistant":
        raise BadRequest("只能对助手消息重新生成")
    rows = db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    ).scalars().all()
    idx = next(i for i, m in enumerate(rows) if m.id == message_id)
    user_msg = next((m for m in reversed(rows[:idx]) if m.role == "user"), None)
    if user_msg is None:
        raise BadRequest("找不到对应的用户问题")
    settings = get_settings()
    history = [{"role": m.role, "content": m.content} for m in rows[: rows.index(user_msg)] if m.content]
    history = history[-(settings.history_rounds * 2) :]
    for m in rows[idx:]:
        db.delete(m)
    conv.updated_at = utcnow()
    db.commit()
    return ChatContext(
        conversation_id=conversation_id,
        question=user_msg.content,
        rewritten=user_msg.content,
        history=history,
        assistant_message_id=new_id(),
    )


async def rewrite(ctx: ChatContext) -> None:
    """F2-8: rewrite with history; fall back to the original question on any failure."""
    if not ctx.history:
        return
    try:
        text, usage = await llm.rewrite_query(build_rewrite_messages(ctx.history, ctx.question))
        ctx.rewrite_usage = usage
        text = text.strip().strip("「」\"'“”")
        if text:
            ctx.rewritten = text.splitlines()[0].strip() or ctx.question
    except Exception as exc:
        log.warning("query rewrite failed, using original question: %s", exc)


def _save_assistant(ctx: ChatContext, content: str, citations: list[dict], usage: llm.Usage, status: str) -> None:
    db = SessionLocal()
    try:
        conv = db.get(Conversation, ctx.conversation_id)
        if conv is None:
            return
        db.add(
            Message(
                id=ctx.assistant_message_id,
                conversation_id=ctx.conversation_id,
                role="assistant",
                content=content,
                citations=citations,
                prompt_tokens=ctx.rewrite_usage.prompt_tokens + usage.prompt_tokens,
                completion_tokens=ctx.rewrite_usage.completion_tokens + usage.completion_tokens,
                status=status,
            )
        )
        conv.updated_at = utcnow()
        db.commit()
    finally:
        db.close()


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def run_complete(ctx: ChatContext) -> dict:
    """Non-streaming answer (M1, kept afterwards)."""
    await rewrite(ctx)
    retrieval: RetrievalResult = await retrieve(ctx.rewritten)
    if retrieval.refused:
        _save_assistant(ctx, REFUSAL_TEXT, [], llm.Usage(), "completed")
        return _complete_payload(ctx, REFUSAL_TEXT, [], llm.Usage(), "completed")
    citations = retrieval.citations()
    messages = build_generation_messages(ctx.history, ctx.question, ctx.rewritten, retrieval.candidates)
    try:
        text, usage = await llm.complete(messages)
    except AppError as exc:
        _save_assistant(ctx, "", citations, llm.Usage(), "error")
        raise exc
    _save_assistant(ctx, text, citations, usage, "completed")
    return _complete_payload(ctx, text, citations, usage, "completed")


def _complete_payload(ctx: ChatContext, text: str, citations: list[dict], usage: llm.Usage, status: str) -> dict:
    return {
        "message_id": ctx.assistant_message_id,
        "content": text,
        "citations": citations,
        "prompt_tokens": ctx.rewrite_usage.prompt_tokens + usage.prompt_tokens,
        "completion_tokens": ctx.rewrite_usage.completion_tokens + usage.completion_tokens,
        "status": status,
    }


async def run_stream(ctx: ChatContext) -> AsyncIterator[str]:
    """SSE generator: citations -> delta* -> done | error."""
    cancel = asyncio.Event()
    _cancel_flags[ctx.assistant_message_id] = cancel
    collected: list[str] = []
    citations: list[dict] = []
    stream_result = llm.StreamResult()
    status = "completed"
    saved = False

    def save(final_status: str) -> None:
        nonlocal saved
        if saved:
            return
        saved = True
        _save_assistant(ctx, "".join(collected), citations, stream_result.usage, final_status)

    try:
        await rewrite(ctx)
        retrieval = await retrieve(ctx.rewritten)
        if retrieval.refused:
            collected.append(REFUSAL_TEXT)
            yield _sse("delta", {"content": REFUSAL_TEXT})
            save("completed")
            yield _sse(
                "done",
                {
                    "message_id": ctx.assistant_message_id,
                    "prompt_tokens": ctx.rewrite_usage.prompt_tokens,
                    "completion_tokens": ctx.rewrite_usage.completion_tokens,
                    "status": "completed",
                },
            )
            return

        citations = retrieval.citations()
        yield _sse("citations", {"citations": citations})

        messages = build_generation_messages(ctx.history, ctx.question, ctx.rewritten, retrieval.candidates)
        upstream = llm.stream(messages, stream_result)
        try:
            async for delta in upstream:
                if cancel.is_set():
                    status = "stopped"
                    break
                collected.append(delta)
                yield _sse("delta", {"content": delta})
        finally:
            await upstream.aclose()
        save(status)
        yield _sse(
            "done",
            {
                "message_id": ctx.assistant_message_id,
                "prompt_tokens": ctx.rewrite_usage.prompt_tokens + stream_result.usage.prompt_tokens,
                "completion_tokens": ctx.rewrite_usage.completion_tokens + stream_result.usage.completion_tokens,
                "status": status,
            },
        )
    except AppError as exc:
        save("error")
        yield _sse("error", {"code": exc.code, "message": exc.message})
    except (asyncio.CancelledError, GeneratorExit):
        # client disconnected
        save("stopped")
        raise
    except Exception as exc:
        log.exception("chat stream failed")
        save("error")
        yield _sse("error", {"code": 500, "message": "服务内部错误", "detail": str(exc)})
    finally:
        save("stopped")  # no-op when already saved
        _cancel_flags.pop(ctx.assistant_message_id, None)
