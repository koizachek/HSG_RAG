from __future__ import annotations

from time import sleep
from typing import Iterable

from ..config import config

MAX_EMBEDDING_ATTEMPTS = 3


class EmbeddingError(RuntimeError):
    pass


class OpenRouterEmbeddingClient:
    def __init__(self) -> None:
        self._client = None

    @property
    def client(self):
        if self._client is None:
            if not config.processing.EMBEDDING_API_KEY:
                raise EmbeddingError("OPEN_ROUTER_API_KEY is not configured for embeddings")

            from openai import OpenAI

            self._client = OpenAI(
                api_key=config.processing.EMBEDDING_API_KEY,
                base_url=config.processing.EMBEDDING_BASE_URL,
            )

        return self._client

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def embed_documents(self, texts: Iterable[str]) -> list[list[float]]:
        clean_texts = [(text or " ").strip() or " " for text in texts]
        if not clean_texts:
            return []

        last_error: Exception | None = None
        for attempt in range(1, MAX_EMBEDDING_ATTEMPTS + 1):
            try:
                response = self.client.embeddings.create(
                    model=config.processing.EMBEDDING_MODEL,
                    input=clean_texts,
                )
                embeddings = self._extract_embeddings(response)
                self._validate_embeddings(embeddings, expected_count=len(clean_texts))
                return embeddings
            except Exception as exc:
                last_error = exc
                if attempt == MAX_EMBEDDING_ATTEMPTS or not self._is_retryable(exc):
                    break
                sleep(min(2 ** (attempt - 1), 8))

        raise EmbeddingError(f"Failed to generate OpenRouter embeddings: {last_error}") from last_error

    @staticmethod
    def _extract_embeddings(response) -> list[list[float]]:
        data = list(getattr(response, "data", []) or [])
        data.sort(key=lambda item: getattr(item, "index", 0))
        return [list(getattr(item, "embedding", []) or []) for item in data]

    def _validate_embeddings(self, embeddings: list[list[float]], expected_count: int) -> None:
        if len(embeddings) != expected_count:
            raise EmbeddingError(
                f"Embedding response count mismatch: expected {expected_count}, got {len(embeddings)}"
            )

        for idx, embedding in enumerate(embeddings):
            if len(embedding) != config.processing.EMBEDDING_DIMENSIONS:
                raise EmbeddingError(
                    f"Embedding {idx} has dimension {len(embedding)}; "
                    f"expected {config.processing.EMBEDDING_DIMENSIONS}"
                )

    @staticmethod
    def _is_retryable(error: Exception) -> bool:
        status_code = getattr(error, "status_code", None)
        if status_code in {408, 409, 425, 429, 500, 502, 503, 504}:
            return True

        text = str(error).lower()
        return any(
            signal in text
            for signal in [
                "rate limit",
                "timeout",
                "temporarily unavailable",
                "connection",
                "server error",
            ]
        )
