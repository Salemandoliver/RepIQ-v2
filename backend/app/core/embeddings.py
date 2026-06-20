"""Embeddings — RepIQ's semantic memory (Roadmap Phase 0).

Turns text (call analyses, notes) into vectors so the app can *retrieve relevant evidence* for any
question — the mechanism by which Ask RepIQ gets smarter the longer it runs. Provider‑agnostic
(OpenAI or Voyage), called over plain HTTP (no extra dependency), and **inert until an API key is
set** in env, so it never breaks a deploy.

Vectors are stored as JSON and searched with brute‑force cosine in Python — perfectly fine at the
company's scale, and with zero database extension to install. (Swap to pgvector + an index later if
call volume makes brute force slow.)
"""
from __future__ import annotations

import json
import math
import urllib.request

from ..config import settings

# Anthropic doesn't make an embeddings model; it recommends Voyage AI (an Anthropic company), so
# Voyage is the default — keeps everything in the Anthropic ecosystem. OpenAI also supported.
_DEFAULT_MODEL = {"voyage": "voyage-3.5-lite", "openai": "text-embedding-3-small"}
_ENDPOINT = {"voyage": "https://api.voyageai.com/v1/embeddings",
             "openai": "https://api.openai.com/v1/embeddings"}


def configured() -> bool:
    return bool(settings.embeddings_provider and settings.embeddings_api_key
               and settings.embeddings_provider in _ENDPOINT)


def model_name() -> str:
    return settings.embeddings_model or _DEFAULT_MODEL.get(settings.embeddings_provider, "")


def embed(texts: list[str], input_type: str | None = None) -> list[list[float]] | None:
    """Return one vector per input text, or None if embeddings aren't configured / the call fails.
    ``input_type`` ('document' | 'query') is a Voyage feature that sharpens retrieval."""
    if not configured() or not texts:
        return None
    provider = settings.embeddings_provider
    body = {"model": model_name(), "input": texts}
    if provider == "voyage" and input_type:
        body["input_type"] = input_type
    req = urllib.request.Request(
        _ENDPOINT[provider], data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {settings.embeddings_api_key}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        # Both providers return {"data": [{"embedding": [...]}, ...]} (input order preserved).
        return [row["embedding"] for row in data.get("data", [])]
    except Exception:
        return None


def embed_one(text: str, input_type: str | None = None) -> list[float] | None:
    out = embed([text], input_type=input_type)
    return out[0] if out else None


# --------------------------------------------------------------- similarity (brute force)
def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def top_k(query_vec: list[float], items: list[tuple], k: int = 8) -> list[tuple]:
    """items = [(id, vector), ...] → the k most similar [(id, score), ...] (highest first)."""
    scored = [(i, cosine(query_vec, v)) for i, v in items if v]
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored[:k]
