from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import NotFound, ok
from ..models import Conversation, Message
from ..schemas import ChatRequest, MessageIdRequest
from ..services import chat_service

router = APIRouter(prefix="/conversations", tags=["conversations"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


@router.get("")
def list_conversations(db: Session = Depends(get_db)):
    rows = db.execute(select(Conversation).order_by(Conversation.updated_at.desc())).scalars().all()
    return ok([c.to_dict() for c in rows])


@router.post("")
def create_conversation(db: Session = Depends(get_db)):
    conv = Conversation(title="新会话")
    db.add(conv)
    db.commit()
    return ok(conv.to_dict(), status_code=201)


@router.delete("/{conversation_id}")
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)):
    conv = db.get(Conversation, conversation_id)
    if conv is None:
        raise NotFound("会话不存在")
    db.delete(conv)
    db.commit()
    return ok({"deleted": True})


@router.get("/{conversation_id}/messages")
def list_messages(conversation_id: str, db: Session = Depends(get_db)):
    conv = db.get(Conversation, conversation_id)
    if conv is None:
        raise NotFound("会话不存在")
    rows = db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    ).scalars().all()
    return ok([m.to_dict() for m in rows])


@router.post("/{conversation_id}/chat/complete")
async def chat_complete(conversation_id: str, body: ChatRequest, db: Session = Depends(get_db)):
    ctx = chat_service.start_turn(db, conversation_id, body.question)
    db.close()
    data = await chat_service.run_complete(ctx)
    return ok(data)


def _stream_response(ctx: chat_service.ChatContext) -> StreamingResponse:
    headers = dict(SSE_HEADERS)
    headers["X-Assistant-Message-Id"] = ctx.assistant_message_id
    return StreamingResponse(chat_service.run_stream(ctx), media_type="text/event-stream", headers=headers)


@router.post("/{conversation_id}/chat")
async def chat_stream(conversation_id: str, body: ChatRequest, db: Session = Depends(get_db)):
    ctx = chat_service.start_turn(db, conversation_id, body.question)
    db.close()
    return _stream_response(ctx)


@router.post("/{conversation_id}/stop")
def chat_stop(conversation_id: str, body: MessageIdRequest, db: Session = Depends(get_db)):
    if db.get(Conversation, conversation_id) is None:
        raise NotFound("会话不存在")
    return ok({"stopped": chat_service.request_stop(body.message_id)})


@router.post("/{conversation_id}/regenerate")
async def chat_regenerate(conversation_id: str, body: MessageIdRequest, db: Session = Depends(get_db)):
    ctx = chat_service.start_regenerate(db, conversation_id, body.message_id)
    db.close()
    return _stream_response(ctx)
