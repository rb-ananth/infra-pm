
import httpx
import math
from app.core.config import settings


class EmbeddingServiceError(RuntimeError):
    """Raised when Ollama cannot generate a valid embedding."""


def generate_embedding(text: str) -> list[float]:
    """Generate an embedding using the configured Ollama model."""

    if not text or not text.strip():
        raise ValueError("Cannot generate an embedding for empty text.")

    url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/embed"

    payload = {
        "model": settings.OLLAMA_EMBEDDING_MODEL,
        "input": text,
    }

    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise EmbeddingServiceError(
            f"Failed to generate embedding using Ollama: {exc}"
        ) from exc

    embeddings = result.get("embeddings")

    if not embeddings or not isinstance(embeddings[0], list):
        raise EmbeddingServiceError(
            "Ollama returned no valid embedding vector."
        )

    embedding = embeddings[0]

    if len(embedding) != settings.OLLAMA_EMBEDDING_DIMENSIONS:
        raise EmbeddingServiceError(
            f"Expected {settings.OLLAMA_EMBEDDING_DIMENSIONS} dimensions, "
            f"but received {len(embedding)}."
        )

    if not all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        for value in embedding
    ):
        raise EmbeddingServiceError(
            "Ollama returned invalid embedding values."
        )

    return [float(value) for value in embedding]
