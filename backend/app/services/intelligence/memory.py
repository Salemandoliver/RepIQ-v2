"""Semantic memory pipeline (Roadmap Phase 0).

Embeds analysed calls into ``CallEmbedding`` so RepIQ can retrieve relevant evidence for any
question (the engine behind a smarter Ask RepIQ over time). Runs from the worker, in batches, and
is **inert until an embeddings provider is configured** — so it's safe to ship now and switch on
later by setting the env vars.
"""
from __future__ import annotations

from sqlalchemy.orm import joinedload

from ...config import settings
from ...core import embeddings
from ...models import Call, CallEmbedding


def _text_for(c: Call) -> str:
    a = c.analysis
    parts: list[str] = []
    who = c.customer_company or c.customer_name
    if who:
        parts.append(f"Customer: {who}")
    if c.activity_type:
        parts.append(f"Type: {c.activity_type}")
    if a is not None:
        if getattr(a, "summary", None):
            parts.append(str(a.summary))
        for p in (getattr(a, "summary_points", None) or [])[:8]:
            parts.append(f"- {p}")
        for s in (getattr(a, "strengths", None) or [])[:5]:
            parts.append(f"strength: {s}")
        for s in (getattr(a, "improvements", None) or [])[:5]:
            parts.append(f"improve: {s}")
    return "\n".join(parts)[:6000]


def embed_pending(db, limit: int | None = None) -> int:
    """Embed a batch of analysed-but-unembedded calls. Returns how many were embedded."""
    if not embeddings.configured():
        return 0
    limit = limit or settings.embeddings_batch
    embedded_ids = db.query(CallEmbedding.call_id)
    calls = (db.query(Call).options(joinedload(Call.analysis))
             .filter(Call.status == "completed", Call.id.notin_(embedded_ids))
             .filter(Call.analysis.has())
             .order_by(Call.started_at.desc()).limit(limit).all())
    n = 0
    for c in calls:
        text = _text_for(c)
        if not text.strip():
            continue
        vec = embeddings.embed_one(text, input_type="document")
        if not vec:
            break                      # provider down — try again next tick
        db.add(CallEmbedding(call_id=c.id, model=embeddings.model_name(), dim=len(vec), vector=vec))
        n += 1
    if n:
        db.commit()
    return n


def search(db, query: str, k: int = 8) -> list[dict]:
    """Most semantically relevant calls to a free-text query → [{callId, score}]. []
    when embeddings aren't configured."""
    if not embeddings.configured() or not (query or "").strip():
        return []
    qv = embeddings.embed_one(query, input_type="query")
    if not qv:
        return []
    items = [(e.call_id, e.vector) for e in db.query(CallEmbedding).all()]
    return [{"callId": cid, "score": round(score, 3)} for cid, score in embeddings.top_k(qv, items, k)]


def status(db) -> dict:
    return {"configured": embeddings.configured(), "provider": settings.embeddings_provider or None,
            "model": embeddings.model_name() or None, "embedded": db.query(CallEmbedding.call_id).count()}
