"""Tiny TTL cache for CompanyIQ (Brief Section 6.4).

Uses Redis when ``REDIS_URL`` is set, otherwise an in-process dict with per-key expiry.
The in-process cache is fine for a single-container pilot; swap REDIS_URL in to share the
cache across workers/replicas without any code change.
"""
from __future__ import annotations

import json
import time
import threading

from ...config import settings

_lock = threading.Lock()
_store: dict[str, tuple[float, str]] = {}   # key -> (expires_at, json_string)
_redis = None
_redis_tried = False


def _get_redis():
    global _redis, _redis_tried
    if _redis_tried:
        return _redis
    _redis_tried = True
    if settings.redis_url:
        try:
            import redis  # optional dependency
            _redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            _redis.ping()
        except Exception:
            _redis = None
    return _redis


def get(key: str):
    r = _get_redis()
    if r is not None:
        try:
            raw = r.get(key)
            return json.loads(raw) if raw else None
        except Exception:
            return None
    with _lock:
        item = _store.get(key)
        if not item:
            return None
        expires_at, raw = item
        if expires_at < time.time():
            _store.pop(key, None)
            return None
        return json.loads(raw)


def set(key: str, value, ttl: int) -> None:
    raw = json.dumps(value, default=str)
    r = _get_redis()
    if r is not None:
        try:
            r.set(key, raw, ex=ttl)
            return
        except Exception:
            pass
    with _lock:
        _store[key] = (time.time() + ttl, raw)


def delete(key: str) -> None:
    r = _get_redis()
    if r is not None:
        try:
            r.delete(key)
        except Exception:
            pass
    with _lock:
        _store.pop(key, None)
