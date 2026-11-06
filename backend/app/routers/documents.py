from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..errors import NotFound, ok
from ..models import Chunk, Document
from ..schemas import ReindexRequest
from ..services import document_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("")
async def upload_document(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    data = await file.read()
    filename = file.filename or "unnamed"
    file_type, parsed = document_service.validate_upload(filename, data)

    doc = Document(
        filename=filename,
        file_type=file_type,
        file_size=len(data),
        storage_path="",
        status="processing",
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    db.add(doc)
    db.flush()
    path = document_service.save_file(doc.id, file_type, data)
    doc.storage_path = str(path)
    if parsed.is_empty:
        doc.status = "failed"
        doc.error_msg = "未抽出文本，当前只支持文本型 PDF"
        db.commit()
        return ok(doc.to_dict(), status_code=201)
    db.commit()
    background.add_task(document_service.ingest, doc.id, parsed)
    return ok(doc.to_dict(), status_code=201)


@router.get("")
def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    total = db.scalar(select(func.count()).select_from(Document)) or 0
    rows = (
        db.execute(select(Document).order_by(Document.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
        .scalars()
        .all()
    )
    return ok({"items": [d.to_dict() for d in rows], "total": total, "page": page, "page_size": page_size})


@router.get("/{document_id}")
def get_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if doc is None:
        raise NotFound("文档不存在")
    return ok(doc.to_dict())


@router.get("/{document_id}/chunks/{chunk_id}")
def get_chunk(document_id: str, chunk_id: str, db: Session = Depends(get_db)):
    chunk = db.get(Chunk, chunk_id)
    if chunk is None or chunk.document_id != document_id:
        raise NotFound("片段不存在")
    return ok(chunk.to_dict())


@router.delete("/{document_id}")
def delete_document(document_id: str, db: Session = Depends(get_db)):
    document_service.delete_document(db, document_id)
    return ok({"deleted": True})


@router.post("/{document_id}/reindex")
def reindex_document(
    document_id: str,
    body: ReindexRequest | None = None,
    background: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    body = body or ReindexRequest()
    doc = document_service.prepare_reindex(db, document_id, body.chunk_size, body.chunk_overlap)
    background.add_task(document_service.ingest, doc.id, None)
    return ok(doc.to_dict())
