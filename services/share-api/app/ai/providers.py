"""Proveedores de IA detrás de interfaces pequeñas: embeddings (Vertex AI) y LLM (Claude).

Los tests y el perfil local sin GCP usan ``FakeEmbedder``, determinista y sin red.
"""

from __future__ import annotations

import hashlib
import math
import re
import time
from typing import Any, Protocol

import httpx

EMBEDDING_DIM = 768
_WORD = re.compile(r"[a-záéíóúñü0-9]+", re.IGNORECASE)


class EmbeddingError(RuntimeError):
    pass


class Embedder(Protocol):
    @property
    def model(self) -> str: ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class FakeEmbedder:
    """Bolsa de palabras con hashing: textos con palabras en común quedan cerca. Sin red."""

    model = "fake-hashing-768"

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIM
        for word in _WORD.findall(text.casefold()):
            if len(word) < 3:
                continue
            digest = hashlib.sha256(word[:6].encode()).digest()
            vector[int.from_bytes(digest[:4], "big") % EMBEDDING_DIM] += 1.0
        return _normalize(vector)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class VertexEmbedder:
    """Embeddings de Vertex AI (``gemini-embedding-001``, 768 dimensiones) vía REST.

    Credenciales: Application Default Credentials (cuenta de servicio en Cloud Run, ``gcloud auth
    application-default login`` en local). Los textos no salen de GCP.
    """

    BATCH = 16

    def __init__(self, *, project: str, location: str, model: str, timeout: float = 30.0) -> None:
        self._url = (
            f"https://{location}-aiplatform.googleapis.com/v1/projects/{project}"
            f"/locations/{location}/publishers/google/models/{model}:predict"
        )
        self._model = model
        self._client = httpx.Client(timeout=timeout)
        self._credentials: Any = None

    @property
    def model(self) -> str:
        return self._model

    def _token(self) -> str:
        import google.auth
        import google.auth.transport.requests

        if self._credentials is None:
            self._credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
        if not self._credentials.valid:
            self._credentials.refresh(google.auth.transport.requests.Request())
        token: str = self._credentials.token
        return token

    def _predict(self, texts: list[str], task_type: str) -> list[list[float]]:
        body = {
            "instances": [{"content": t, "task_type": task_type} for t in texts],
            "parameters": {"outputDimensionality": EMBEDDING_DIM, "autoTruncate": True},
        }
        for attempt in range(3):
            response = self._client.post(
                self._url, json=body, headers={"Authorization": f"Bearer {self._token()}"}
            )
            if response.status_code == 429 or response.status_code >= 500:
                time.sleep(1.5 * (attempt + 1))
                continue
            if not response.is_success:
                raise EmbeddingError(f"Vertex respondió {response.status_code}")
            predictions = response.json()["predictions"]
            return [_normalize(p["embeddings"]["values"]) for p in predictions]
        raise EmbeddingError("Vertex no respondió tras varios intentos")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.BATCH):
            vectors.extend(self._predict(texts[start : start + self.BATCH], "RETRIEVAL_DOCUMENT"))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._predict([text], "RETRIEVAL_QUERY")[0]
