"""Object storage for HR documents (brief §13).

Primary backend is **Cloudflare R2** (S3-compatible) when configured in env; otherwise files are
stored durably in the database (a `bytea` blob) — fine for the current scale and capped per file.
The rest of the app calls ``save`` / ``load`` / ``remove`` and doesn't care which backend is live;
each document row records its own ``backend`` so old files keep working after R2 is switched on.
"""
from __future__ import annotations

import uuid

from ..config import settings

R2 = "r2"
DB = "db"


def r2_configured() -> bool:
    return bool(settings.r2_account_id and settings.r2_access_key_id
               and settings.r2_secret_access_key and settings.r2_bucket)


def active_backend() -> str:
    return R2 if r2_configured() else DB


def _r2_client():
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


def new_key(prefix: str, filename: str) -> str:
    safe = "".join(c for c in (filename or "file") if c.isalnum() or c in "._- ").strip() or "file"
    return f"{prefix}/{uuid.uuid4().hex}/{safe}"


def save(key: str, data: bytes, content_type: str | None = None) -> str:
    """Persist bytes under ``key``; returns the backend used ('r2' or 'db').
    For the DB backend the caller stores the bytes themselves (we just report the backend)."""
    if r2_configured():
        _r2_client().put_object(Bucket=settings.r2_bucket, Key=key, Body=data,
                                ContentType=content_type or "application/octet-stream")
        return R2
    return DB


def load(backend: str, key: str) -> bytes:
    """Fetch bytes for an R2-backed object. DB-backed bytes are read by the caller from the blob
    table (we don't have DB access here), so this only handles R2."""
    if backend == R2:
        obj = _r2_client().get_object(Bucket=settings.r2_bucket, Key=key)
        return obj["Body"].read()
    raise ValueError("DB-backed documents are loaded from the database, not storage.load()")


def remove(backend: str, key: str) -> None:
    if backend == R2:
        try:
            _r2_client().delete_object(Bucket=settings.r2_bucket, Key=key)
        except Exception:
            pass


def status() -> dict:
    return {"backend": active_backend(), "configured": r2_configured(),
            "bucket": settings.r2_bucket or None, "account": settings.r2_account_id or None}


def test_roundtrip() -> dict:
    """Admin diagnostics: write, read back, and delete a tiny test object in R2, so credentials
    and the bucket can be verified without uploading a real document."""
    if not r2_configured():
        return {"ok": False, "backend": DB,
                "detail": "R2 isn't configured — documents are stored in the app database. "
                          "Set R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_BUCKET to use R2."}
    key = f"hr/_diagnostics/{uuid.uuid4().hex}.txt"
    payload = b"repiq-storage-test"
    try:
        c = _r2_client()
        c.put_object(Bucket=settings.r2_bucket, Key=key, Body=payload, ContentType="text/plain")
        got = c.get_object(Bucket=settings.r2_bucket, Key=key)["Body"].read()
        c.delete_object(Bucket=settings.r2_bucket, Key=key)
        if got != payload:
            return {"ok": False, "backend": R2, "detail": "Round-trip mismatch — read data did not match."}
        return {"ok": True, "backend": R2,
                "detail": f"Wrote, read and deleted a test object in bucket '{settings.r2_bucket}'."}
    except Exception as e:
        return {"ok": False, "backend": R2, "detail": f"{type(e).__name__}: {str(e)[:300]}"}
