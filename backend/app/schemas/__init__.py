from __future__ import annotations

from pydantic import BaseModel, Field


class ReindexRequest(BaseModel):
    chunk_size: int | None = Field(default=None, ge=50, le=5000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=2000)


class ChatRequest(BaseModel):
    question: str


class MessageIdRequest(BaseModel):
    message_id: str


class EvalRunRequest(BaseModel):
    chunk_size: int | None = Field(default=None, ge=50, le=5000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=2000)
    use_hybrid: bool | None = None
    use_rerank: bool | None = None
    k: int | None = Field(default=None, ge=1, le=50)
