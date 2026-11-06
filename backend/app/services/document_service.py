"""Upload validation and the ingest pipeline (parse -> chunk -> embed -> store)."""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import delete, select

from ..config import get_settings
from ..db import SessionLocal
from ..errors import BadRequest, NotFound, UnprocessableFile
from ..models import Chunk, Document, new_id
from . import bm25_index, embedding, vector_store
from .chunker import split_document
from .parser import ParsedDocument, check_magic, detect_file_type, parse_document

log = logging.getLogger("rag.documents")


def validate_upload(filename: str, data: bytes) -> tuple[str, ParsedDocument]:
    settings = get_settings()
    file_type = detect_file_type(filename)
    if not data:
        raise UnprocessableFile("文件为空")
    if len(data) > settings.max_upload_bytes:
        raise BadRequest("文件超过 20MB 限制", detail={"size": len(data)})
    check_magic(file_type, data)
    parsed = parse_document(file_type, data)
    return file_type, parsed


def save_file(document_id: str, file_type: str, data: bytes) -> Path:
    settings = get_settings()
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    path = settings.upload_path / f"{document_id}.{file_type}"
    path.write_bytes(data)
    return path


def _clear_document_index(db, document_id: str) -> None:
    vector_store.delete_document(document_id)
    db.execute(delete(Chunk).where(Chunk.document_id == document_id))


def ingest(document_id: str, parsed: ParsedDocument | None = None) -> None:
    """Runs in a background thread. Writes chunks + vectors, then flips the document status."""
    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if doc is None:
            return
        try:
            if parsed is None:
                data = Path(doc.storage_path).read_bytes()
                parsed = parse_document(doc.file_type, data)
            if parsed.is_empty:
                raise UnprocessableFile("未抽出文本，当前只支持文本型 PDF")

            _clear_document_index(db, document_id)
            db.commit()

            pieces = split_document(parsed, doc.chunk_size, doc.chunk_overlap)
            if not pieces:
                raise UnprocessableFile("切分后没有有效文本")

            ids = [new_id() for _ in pieces]
            vectors = embedding.embed_passages([p.content for p in pieces])
            metadatas = []
            for p in pieces:
                meta = {
                    "document_id": doc.id,
                    "document_name": doc.filename,
                    "chunk_id": "",
                    "seq": p.seq,
                    "section": p.section or "",
                }
                if p.page_no is not None:
                    meta["page_no"] = p.page_no
                metadatas.append(meta)
            for cid, meta in zip(ids, metadatas):
                meta["chunk_id"] = cid

            vector_store.add(ids, vectors, [p.content for p in pieces], metadatas)
            for cid, p in zip(ids, pieces):
                db.add(
                    Chunk(
                        id=cid,
                        document_id=doc.id,
                        seq=p.seq,
                        content=p.content,
                        char_start=p.char_start,
                        char_end=p.char_end,
                        page_no=p.page_no,
                        section=p.section or "",
                        vector_id=cid,
                    )
                )
            doc.chunk_count = len(pieces)
            doc.status = "ready"
            doc.error_msg = None
            db.commit()
            log.info("document %s ready with %d chunks", doc.id, len(pieces))
        except Exception as exc:
            db.rollback()
            try:
                _clear_document_index(db, document_id)
                doc = db.get(Document, document_id)
                if doc is not None:
                    doc.status = "failed"
                    doc.chunk_count = 0
                    doc.error_msg = exc.message if hasattr(exc, "message") else f"处理失败：{type(exc).__name__}: {exc}"
                db.commit()
            except Exception:
                db.rollback()
            log.exception("document %s failed", document_id)
        finally:
            try:
                bm25_index.rebuild()
            except Exception:
                log.exception("bm25 rebuild failed")
    finally:
        db.close()


def delete_document(db, document_id: str) -> None:
    doc = db.get(Document, document_id)
    if doc is None:
        raise NotFound("文档不存在")
    vector_store.delete_document(document_id)
    path = Path(doc.storage_path)
    db.delete(doc)
    db.commit()
    try:
        if path.exists():
            path.unlink()
    except OSError:
        log.warning("failed to remove %s", path)
    bm25_index.rebuild()


def prepare_reindex(db, document_id: str, chunk_size: int | None, chunk_overlap: int | None) -> Document:
    doc = db.get(Document, document_id)
    if doc is None:
        raise NotFound("文档不存在")
    if doc.status == "processing":
        raise BadRequest("文档正在处理中，请稍后再试")
    if not Path(doc.storage_path).exists():
        raise BadRequest("原始文件已丢失，无法重建索引，请删除后重新上传")
    if chunk_size is not None:
        doc.chunk_size = chunk_size
    if chunk_overlap is not None:
        doc.chunk_overlap = chunk_overlap
    if doc.chunk_overlap >= doc.chunk_size:
        raise BadRequest("chunk_overlap 必须小于 chunk_size")
    doc.status = "processing"
    doc.error_msg = None
    db.commit()
    db.refresh(doc)
    return doc


def reindex_all_ready(chunk_size: int, chunk_overlap: int) -> int:
    """Synchronous full rebuild used by the evaluator. Returns number of documents processed."""
    db = SessionLocal()
    try:
        docs = db.execute(select(Document).where(Document.status == "ready")).scalars().all()
        ids = []
        for doc in docs:
            doc.chunk_size = chunk_size
            doc.chunk_overlap = chunk_overlap
            doc.status = "processing"
            ids.append(doc.id)
        db.commit()
    finally:
        db.close()
    for doc_id in ids:
        ingest(doc_id)
    return len(ids)


def mark_stale_processing_failed() -> None:
    db = SessionLocal()
    try:
        docs = db.execute(select(Document).where(Document.status == "processing")).scalars().all()
        for doc in docs:
            doc.status = "failed"
            doc.error_msg = "服务重启，请删除后重新上传或重建索引"
        db.commit()
    finally:
        db.close()
