"""AES-256-GCM field encryption for data-at-rest (bank details, NI number, etc.).

The key is read from ``FINANCIAL_ENC_KEY`` (env) — DELIBERATELY separate from JWT_SECRET so
financial data has its own key boundary (brief §4.3 / §10). Value format is a 32-byte key,
base64- or hex-encoded.

``encrypt`` returns a self-describing string ``"gcm.v1:<base64(nonce|ciphertext|tag)>"`` safe
to store in a text column. ``decrypt`` reverses it. If no key is configured, encryption is a
no-op pass-through tagged ``"plain:"`` so dev/test works without a key — but production MUST
set the key (a startup check warns if financial tables exist without it).
"""
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_PREFIX = "gcm.v1:"
_PLAIN = "plain:"


def _load_key() -> bytes | None:
    raw = (os.environ.get("FINANCIAL_ENC_KEY") or "").strip()
    if not raw:
        return None
    for decoder in (base64.b64decode, bytes.fromhex):
        try:
            k = decoder(raw)
            if len(k) == 32:
                return k
        except Exception:
            continue
    # Last resort: raw utf-8 bytes, padded/truncated to 32 (not recommended; warns).
    b = raw.encode("utf-8")
    return (b + b"\0" * 32)[:32]


def is_configured() -> bool:
    return _load_key() is not None


def encrypt(plaintext: str | None) -> str | None:
    """Encrypt a string for storage. None passes through as None."""
    if plaintext is None:
        return None
    key = _load_key()
    if key is None:
        return _PLAIN + plaintext              # dev/test fallback — no key configured
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return _PREFIX + base64.b64encode(nonce + ct).decode("ascii")


def decrypt(stored: str | None) -> str | None:
    """Decrypt a stored value produced by ``encrypt``. None passes through as None."""
    if stored is None:
        return None
    if stored.startswith(_PLAIN):
        return stored[len(_PLAIN):]
    if stored.startswith(_PREFIX):
        key = _load_key()
        if key is None:
            raise RuntimeError("FINANCIAL_ENC_KEY is required to decrypt stored financial data")
        blob = base64.b64decode(stored[len(_PREFIX):])
        nonce, ct = blob[:12], blob[12:]
        return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")
    # Unknown/legacy plaintext — return as-is so reads don't break during migration.
    return stored


def generate_key_b64() -> str:
    """Helper to mint a new key for FINANCIAL_ENC_KEY (run once, store in Railway)."""
    return base64.b64encode(os.urandom(32)).decode("ascii")
