from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_base_url: str = "https://llm-dinftn7ztwksq2qd.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    llm_api_key: str = ""
    llm_model: str = "kimi-k3"

    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_backend: str = "fastembed"  # fastembed | sentence-transformers | auto
    embedding_device: str = "cpu"
    embedding_query_instruction: str = "为这个句子生成表示以用于检索相关文章："

    cohere_api_key: str = ""
    rerank_model: str = "rerank-v3.5"
    rerank_base_url: str = "https://api.cohere.com/v2/rerank"
    rerank_enabled: bool = False
    # seconds between rerank calls during evaluation; Cohere trial keys allow 10 calls / minute
    rerank_eval_interval: float = 6.5

    chroma_dir: str = "storage/chroma"
    sqlite_url: str = "sqlite:///storage/app.db"
    upload_dir: str = "storage/uploads"

    chunk_size: int = 500
    chunk_overlap: int = 50
    top_k: int = 5
    recall_k: int = 20
    rrf_k: int = 60
    vector_threshold: float = 0.40
    rerank_threshold: float = 0.2
    history_rounds: int = 5
    use_hybrid: bool = True

    cors_origins: str = "http://localhost:5173"

    max_upload_bytes: int = 20 * 1024 * 1024
    max_question_chars: int = 2000

    def resolve(self, relative: str) -> Path:
        path = Path(relative)
        if not path.is_absolute():
            path = BASE_DIR / path
        return path

    @property
    def chroma_path(self) -> Path:
        return self.resolve(self.chroma_dir)

    @property
    def upload_path(self) -> Path:
        return self.resolve(self.upload_dir)

    @property
    def sqlalchemy_url(self) -> str:
        prefix = "sqlite:///"
        if self.sqlite_url.startswith(prefix):
            raw = self.sqlite_url[len(prefix):]
            if raw and raw != ":memory:" and not Path(raw).is_absolute():
                return prefix + (BASE_DIR / raw).as_posix()
        return self.sqlite_url

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def evals_dir(self) -> Path:
        return BASE_DIR / "evals"


@lru_cache
def get_settings() -> Settings:
    return Settings()
