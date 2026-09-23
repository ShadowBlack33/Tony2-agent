"""Embeddings de texto con cache en disco.

- LiteLLMEmbedder: cualquier proveedor soportado por LiteLLM (ej. gemini/gemini-embedding-001).
- Cache por (modelo, hash del texto): el catalogo solo se re-embebe cuando cambia.
- StubEmbedder: vectores fijos para tests, sin API.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import numpy as np

log = logging.getLogger(__name__)


class Embedder(Protocol):
    model: str

    def embed(self, texts: list[str]) -> np.ndarray: ...


def _unit(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


class LiteLLMEmbedder:
    def __init__(self, model: str, batch_size: int = 64):
        import litellm
        self._litellm, self.model, self.batch_size = litellm, model, batch_size

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            resp = self._litellm.embedding(model=self.model, input=texts[i:i + self.batch_size])
            for item in resp.data:
                vectors.append(item["embedding"] if isinstance(item, dict) else item.embedding)
        return _unit(np.asarray(vectors, dtype=np.float32))


class StubEmbedder:
    """Para tests: devuelve el vector asignado a cada texto (o cero)."""

    def __init__(self, table: dict[str, list[float]], dim: int, model: str = "stub"):
        self.table, self.dim, self.model = table, dim, model

    def embed(self, texts: list[str]) -> np.ndarray:
        rows = [self.table.get(t, [0.0] * self.dim) for t in texts]
        return _unit(np.asarray(rows, dtype=np.float32))


class CachedEmbedder:
    """Envuelve un Embedder con cache persistente (documentos) y LRU en memoria (consultas)."""

    def __init__(self, inner: Embedder, cache_path: Path | None):
        self.inner, self.cache_path, self.model = inner, cache_path, inner.model
        self._lock = threading.Lock()
        self._cache: dict[str, list[float]] = {}
        if cache_path and cache_path.exists():
            try:
                data = json.loads(cache_path.read_text(encoding="utf-8"))
                if data.get("model") == self.model:
                    self._cache = data["vectors"]
            except (json.JSONDecodeError, KeyError):
                log.warning("Cache de embeddings corrupto; se regenera.")
        self._query = lru_cache(maxsize=512)(self._embed_one)

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        missing = [t for t in texts if self._key(t) not in self._cache]
        if missing:
            vecs = self.inner.embed(missing)
            with self._lock:
                for t, v in zip(missing, vecs):
                    self._cache[self._key(t)] = v.tolist()
                self._persist()
        return np.asarray([self._cache[self._key(t)] for t in texts], dtype=np.float32)

    def _embed_one(self, text: str) -> tuple[float, ...]:
        return tuple(self.inner.embed([text])[0].tolist())

    def embed_query(self, text: str) -> np.ndarray:
        return np.asarray(self._query(text), dtype=np.float32)

    def _persist(self) -> None:
        if self.cache_path:
            self.cache_path.write_text(json.dumps({"model": self.model, "vectors": self._cache}), encoding="utf-8")
