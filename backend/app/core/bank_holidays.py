"""UK bank holidays (England & Wales — the company's jurisdiction).

Used app-wide so bank holidays aren't counted as leave or as selling days, and are marked on the
holiday calendar. Fetches the authoritative list from gov.uk (cached for a week) and falls back to
a hardcoded table if the network is unavailable, so it always returns something sensible.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request
from datetime import date

_URL = "https://www.gov.uk/bank-holidays.json"
_DIVISION = "england-and-wales"
_TTL = 7 * 24 * 3600

_lock = threading.Lock()
_cache: dict = {"loaded_at": 0.0, "dates": None}

# Fallback (England & Wales) for 2025–2027 — overridden by the live gov.uk feed when reachable.
_FALLBACK = {
    2025: ["2025-01-01", "2025-04-18", "2025-04-21", "2025-05-05", "2025-05-26",
           "2025-08-25", "2025-12-25", "2025-12-26"],
    2026: ["2026-01-01", "2026-04-03", "2026-04-06", "2026-05-04", "2026-05-25",
           "2026-08-31", "2026-12-25", "2026-12-28"],
    2027: ["2027-01-01", "2027-03-26", "2027-03-29", "2027-05-03", "2027-05-31",
           "2027-08-30", "2027-12-27", "2027-12-28"],
}


def _fallback_dates() -> set[date]:
    out: set[date] = set()
    for days in _FALLBACK.values():
        for s in days:
            out.add(date.fromisoformat(s))
    return out


def _fetch() -> set[date] | None:
    try:
        with urllib.request.urlopen(_URL, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
        events = data.get(_DIVISION, {}).get("events", [])
        out = {date.fromisoformat(e["date"]) for e in events if e.get("date")}
        return out or None
    except Exception:
        return None


def all_dates() -> set[date]:
    """Set of bank-holiday dates (cached, refreshed weekly). Falls back to the hardcoded table."""
    with _lock:
        fresh = _cache["dates"] is not None and (time.time() - _cache["loaded_at"] < _TTL)
        if fresh:
            return _cache["dates"]
        live = _fetch()
        merged = _fallback_dates()
        if live:
            merged = merged | live          # union so we keep fallback years the feed may drop
        _cache.update({"loaded_at": time.time(), "dates": merged})
        return merged


def is_bank_holiday(d: date) -> bool:
    return d in all_dates()


def in_range(start: date, end: date) -> set[date]:
    return {d for d in all_dates() if start <= d <= end}


def count_working_bank_holidays(start: date, end: date) -> int:
    """Bank holidays that fall on a weekday within [start, end] (i.e. that remove a working day)."""
    return sum(1 for d in in_range(start, end) if d.weekday() < 5)
