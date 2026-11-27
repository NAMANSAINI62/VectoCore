"""Embedding service using NVIDIA Nemotron 3.5 Embed 1B via LangChain NVIDIAEmbeddings."""

import asyncio
import threading
from collections import OrderedDict
from functools import lru_cache

from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings

from app.config.settings import get_settings

DEFAULT_MODEL_NAME = "nvidia/nemotron-3.5-embed-1b"
DEFAULT_EMBEDDING_DIM = 2048


class EmbeddingService:
    """Singleton service for generating query embeddings via NVIDIA NIM."""

    _instance: "EmbeddingService | None" = None
    _client: NVIDIAEmbeddings | None = None
    _cache: OrderedDict[str, list[float]] = OrderedDict()
    _cache_lock = threading.RLock()

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME):
        self.model_name = model_name
        self.dim = DEFAULT_EMBEDDING_DIM

    @classmethod
    def get_instance(cls) -> "EmbeddingService":
        if cls._instance is None:
            settings = get_settings()
            cls._instance = cls(model_name=settings.EMBEDDING_MODEL_NAME or DEFAULT_MODEL_NAME)
        return cls._instance

    def _ensure_client(self) -> NVIDIAEmbeddings:
        if self._client is None:
            settings = get_settings()
            api_key = (settings.NVIDIA_EMBED_API_KEY or settings.NVIDIA_API_KEY).strip()
            if not api_key:
                raise RuntimeError("NVIDIA_EMBED_API_KEY is not configured in backend/.env.")
            self._client = NVIDIAEmbeddings(
                model=self.model_name,
                api_key=api_key,
                truncate="END",
            )
        return self._client

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query into a normalized float vector (with in-memory LRU reuse)."""
        text = query.strip()
        if not text:
            raise ValueError("Query string cannot be empty for embedding generation.")
        with self._cache_lock:
            cached = self._cache.get(text)
            if cached is not None:
                self._cache.move_to_end(text)
                return cached
        client = self._ensure_client()
        vector = [float(x) for x in client.embed_query(text)]
        if len(vector) != self.dim:
            raise ValueError(f"Generated embedding dimension {len(vector)} does not match expected {self.dim}.")
        with self._cache_lock:
            self._cache[text] = vector
            if len(self._cache) > 512:
                self._cache.popitem(last=False)
        return vector

    async def aembed_query(self, query: str) -> list[float]:
        """Non-blocking async wrapper so embedding HTTP calls never freeze the FastAPI event loop."""
        return await asyncio.to_thread(self.embed_query, query)


@lru_cache
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService.get_instance()
