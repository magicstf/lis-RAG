from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import Base, engine
from .errors import install_error_handlers, ok
from .routers import conversations, documents, evals, usage
from .services import bm25_index, document_service, embedding

logging.basicConfig(level=logging.INFO, format="%(message)s")
access_log = logging.getLogger("rag.access")
log = logging.getLogger("rag")


def _warm_up() -> None:
    try:
        embedding.load_model()
    except Exception:
        log.exception("embedding warm-up failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    settings.chroma_path.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    document_service.mark_stale_processing_failed()
    try:
        bm25_index.rebuild()
    except Exception:
        log.exception("bm25 initial build failed")
    threading.Thread(target=_warm_up, name="embedding-warmup", daemon=True).start()
    yield


app = FastAPI(title="RAG Knowledge Base", version="1.1", lifespan=lifespan)
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Trace-Id", "X-Assistant-Message-Id"],
)


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4())
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    response.headers["X-Trace-Id"] = trace_id
    access_log.info(
        json.dumps(
            {
                "trace_id": trace_id,
                "path": request.url.path,
                "method": request.method,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
            ensure_ascii=False,
        )
    )
    return response


install_error_handlers(app)

app.include_router(documents.router, prefix="/api")
app.include_router(conversations.router, prefix="/api")
app.include_router(evals.router, prefix="/api")
app.include_router(usage.router, prefix="/api")


@app.get("/api/health")
def health():
    return ok({"status": "ok"})
