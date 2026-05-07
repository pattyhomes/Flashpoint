import json

import httpx

from app.config import settings


def embed_text(text: str) -> str | None:
    """Return a JSON-encoded local embedding, or None if local AI is unavailable.

    The helper is deliberately nullable: ingestion must never fail just because
    Ollama is stopped, busy, or missing a model.
    """
    if not settings.ollama_embeddings_enabled:
        return None
    text = (text or "").strip()
    if not text:
        return None

    try:
        response = httpx.post(
            f"{settings.ollama_base_url.rstrip('/')}/api/embed",
            json={"model": settings.ollama_embedding_model, "input": text},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None

    embeddings = data.get("embeddings")
    if isinstance(embeddings, list) and embeddings:
        return json.dumps(embeddings[0], separators=(",", ":"))
    embedding = data.get("embedding")
    if isinstance(embedding, list):
        return json.dumps(embedding, separators=(",", ":"))
    return None
