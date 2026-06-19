"""Microsoft Graph (Sites.Selected) reader for private SharePoint trackers.

Used when the tenant blocks anonymous "anyone with the link" shares. A dedicated app
registration ("CallIQ Tracker Reader") is granted READ on a single SharePoint site, so
the app can download specific workbooks with no user login and no public exposure.

Configured via SHAREPOINT_* settings (falls back to the Teams MS_* creds). Each tracker
file is addressed by its path inside the document library, e.g.
"Trackers/BTLB Lead Tracker 26.01.26.xlsx". If the exact name drifts (the date in the
filename changes), we fall back to a prefix match within the same folder.
"""
from __future__ import annotations

import logging
import threading
import urllib.parse
from datetime import datetime, timedelta

import httpx

from ...config import settings

log = logging.getLogger("calliq.salesiq.graph")
GRAPH = "https://graph.microsoft.com/v1.0"


def _creds() -> tuple[str, str, str]:
    """(tenant, client_id, client_secret) — dedicated SHAREPOINT_*, else Teams MS_*."""
    return (
        settings.sharepoint_tenant_id or settings.ms_tenant_id,
        settings.sharepoint_client_id or settings.ms_client_id,
        settings.sharepoint_client_secret or settings.ms_client_secret,
    )


def configured() -> bool:
    tenant, cid, secret = _creds()
    return bool(tenant and cid and secret)


_lock = threading.Lock()
_state = {"token": None, "expiry": datetime.min, "site_id": None, "drive_id": None}


def _token() -> str:
    with _lock:
        if _state["token"] and datetime.utcnow() < _state["expiry"]:
            return _state["token"]
        tenant, cid, secret = _creds()
        r = httpx.post(
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            data={"grant_type": "client_credentials", "client_id": cid,
                  "client_secret": secret, "scope": "https://graph.microsoft.com/.default"},
            timeout=30)
        r.raise_for_status()
        d = r.json()
        _state["token"] = d["access_token"]
        _state["expiry"] = datetime.utcnow() + timedelta(seconds=d.get("expires_in", 3600) - 60)
        return _state["token"]


def _get(path: str, **kw) -> httpx.Response:
    return httpx.get(f"{GRAPH}{path}", headers={"Authorization": f"Bearer {_token()}"},
                     timeout=120, **kw)


def _site_id() -> str:
    if _state["site_id"]:
        return _state["site_id"]
    if settings.sharepoint_site_id:
        _state["site_id"] = settings.sharepoint_site_id
        return _state["site_id"]
    r = _get(f"/sites/{settings.sharepoint_site_path}")
    r.raise_for_status()
    _state["site_id"] = r.json()["id"]
    return _state["site_id"]


def _drive_id() -> str:
    """The document library (drive) named SHAREPOINT_LIBRARY; else the site's default drive."""
    if _state["drive_id"]:
        return _state["drive_id"]
    want = (settings.sharepoint_library or "").strip().lower()
    r = _get(f"/sites/{_site_id()}/drives?$select=id,name")
    r.raise_for_status()
    drives = r.json().get("value", [])
    chosen = None
    for d in drives:
        if want and d.get("name", "").strip().lower() == want:
            chosen = d["id"]
            break
    if not chosen:  # fall back to the default document library
        rd = _get(f"/sites/{_site_id()}/drive?$select=id")
        rd.raise_for_status()
        chosen = rd.json()["id"]
    _state["drive_id"] = chosen
    return chosen


def _enc(path: str) -> str:
    """URL-encode each path segment (spaces, etc.) for a Graph :/path: address."""
    return "/".join(urllib.parse.quote(seg) for seg in path.strip("/").split("/"))


def _download_by_prefix(drive_id: str, path: str) -> bytes:
    """If the exact name is gone, match by folder + filename prefix before the date stamp."""
    path = path.strip("/")
    folder, _, fname = path.rpartition("/")
    listing = f"/drives/{drive_id}/root:/{_enc(folder)}:/children" if folder \
        else f"/drives/{drive_id}/root/children"
    r = _get(f"{listing}?$top=999&$select=name,id")
    r.raise_for_status()
    stem = fname.lower()
    for cut in (" ", "."):  # progressively loosen: full stem, then up to first space/dot run
        pref = stem.split(cut)[0]
        if len(pref) < 4:
            continue
        for it in r.json().get("value", []):
            if it.get("name", "").lower().startswith(pref):
                c = _get(f"/drives/{drive_id}/items/{it['id']}/content")
                if c.status_code in (301, 302):
                    c = httpx.get(c.headers["Location"], timeout=300)
                c.raise_for_status()
                return c.content
    raise FileNotFoundError(f"No file matching '{fname}' in '{folder or '/'}'")


def download(path: str) -> bytes:
    """Download a workbook by its library-relative path; prefix-match fallback on 404."""
    drive_id = _drive_id()
    r = _get(f"/drives/{drive_id}/root:/{_enc(path)}:/content")
    if r.status_code in (301, 302):
        r = httpx.get(r.headers["Location"], timeout=300)
    if r.status_code == 404:
        return _download_by_prefix(drive_id, path)
    r.raise_for_status()
    return r.content


def debug() -> dict:
    """Connectivity + what the app can see (for setup verification)."""
    if not configured():
        return {"configured": False}
    out: dict = {"configured": True, "sitePath": settings.sharepoint_site_path,
                 "library": settings.sharepoint_library}
    try:
        out["siteId"] = _site_id()
        r = _get(f"/sites/{_site_id()}/drives?$select=id,name")
        r.raise_for_status()
        out["drives"] = [d.get("name") for d in r.json().get("value", [])]
        out["driveId"] = _drive_id()
        rc = _get(f"/drives/{_drive_id()}/root:/Trackers:/children?$top=999&$select=name")
        out["trackersFolder"] = ([i.get("name") for i in rc.json().get("value", [])]
                                 if rc.status_code == 200 else f"HTTP {rc.status_code}")
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:300]}"
    return out
