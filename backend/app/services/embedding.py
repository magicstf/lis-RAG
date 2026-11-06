"""Local embedding with two interchangeable backends.

- fastembed (default): ONNX runtime, no torch dependency, CPU friendly.
- sentence-transformers: torch based; pick it via EMBEDDING_BACKEND=sentence-transformers.

Both backends return L2-normalised vectors so cosine similarity equals the dot product.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Protocol

from ..config import get_settings
from . import usage

log = logging.getLogger("rag.embedding")

_backend: "_Backend | None" = None
_lock = threading.Lock()
BATCH_SIZE = 32


class _Backend(Protocol):
    def encode(self, texts: list[str]) -> list[list[float]]: ...


class _FastEmbedBackend:
    def __init__(self, model_name: str, cache_dir: str) -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model_name, cache_dir=cache_dir, threads=None)

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(texts, batch_size=BATCH_SIZE)]


class _SentenceTransformersBackend:
    def __init__(self, model_name: str, device: str, cache_dir: str) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name, device=device, cache_folder=cache_dir)

    def encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, batch_size=BATCH_SIZE, normalize_embeddings=True, show_progress_bar=False)
        return [v.tolist() for v in vectors]


def _build_backend() -> _Backend:
    settings = get_settings()
    cache_dir = str(settings.resolve("storage/models"))
    settings.resolve("storage/models").mkdir(parents=True, exist_ok=True)
    choice = settings.embedding_backend.lower()
    started = time.time()
    if choice == "sentence-transformers":
        backend: _Backend = _SentenceTransformersBackend(settings.embedding_model, settings.embedding_device, cache_dir)
    elif choice == "fastembed":
        backend = _FastEmbedBackend(settings.embedding_model, cache_dir)
    else:  # auto: prefer fastembed, fall back to sentence-transformers
        try:
            backend = _FastEmbedBackend(settings.embedding_model, cache_dir)
        except Exception as exc:
            log.warning("fastembed unavailable (%s), falling back to sentence-transformers", exc)
            backend = _SentenceTransformersBackend(settings.embedding_model, settings.embedding_device, cache_dir)
    log.info("embedding model %s ready via %s in %.1fs", settings.embedding_model, type(backend).__name__, time.time() - started)
    return backend


def load_model() -> _Backend:
    global _backend
    if _backend is not None:
        return _backend
    with _lock:
        if _backend is None:
            _backend = _build_backend()
    return _backend


def embed_passages(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    vectors = load_model().encode(texts)
    usage.record("embedding", 0, 0, calls=1)
    return vectors


def embed_query(text: str) -> list[float]:
    settings = get_settings()
    vector = load_model().encode([settings.embedding_query_instruction + text])[0]
    usage.record("embedding", 0, 0, calls=1)
    return vector
