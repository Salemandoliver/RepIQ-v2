"""RingCentral integration: JWT auth, recording download, webhook subscription setup,
historical backfill, with automatic back-off on rate limits."""
import logging
import os
import threading
from datetime import datetime, timedelta

import httpx

from ..config import settings

log = logging.getLogger("calliq.ringcentral")


class RingCentralClient:
    def __init__(self):
        self.base = settings.ringcentral_server_url
        self._token: str | None = None
        self._token_expiry = datetime.min
        # Serialise token refresh: without this, parallel worker threads each request a new
        # token at expiry, and RingCentral revokes the previous one — so in-flight downloads
        # using the now-stale token get 401 Unauthorized. One token, shared, refreshed once.
        self._token_lock = threading.Lock()

    @staticmethod
    def _retry_429(do_request, attempts: int = 4):
        """RingCentral rate-limits aggressively; honour Retry-After and back off."""
        import time as _time
        r = None
        for i in range(attempts):
            r = do_request()
            if r.status_code != 429:
                r.raise_for_status()
                return r
            wait = int(r.headers.get("Retry-After", "60")) + 2
            log.warning("RingCentral 429 — backing off %ss (attempt %d/%d)",
                        wait, i + 1, attempts)
            _time.sleep(min(wait, 120))
        r.raise_for_status()
        return r

    def _auth(self) -> str:
        if self._token and datetime.utcnow() < self._token_expiry:
            return self._token
        with self._token_lock:
            # Re-check inside the lock — another thread may have just refreshed it.
            if self._token and datetime.utcnow() < self._token_expiry:
                return self._token
            resp = self._retry_429(lambda: httpx.post(
                f"{self.base}/restapi/oauth/token",
                data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                      "assertion": settings.ringcentral_jwt},
                auth=(settings.ringcentral_client_id, settings.ringcentral_client_secret),
                timeout=30,
            ))
            data = resp.json()
            self._token = data["access_token"]
            self._token_expiry = datetime.utcnow() + timedelta(seconds=data["expires_in"] - 60)
            return self._token

    def _get(self, path: str, **kwargs) -> httpx.Response:
        return self._retry_429(lambda: httpx.get(
            f"{self.base}{path}",
            headers={"Authorization": f"Bearer {self._auth()}"},
            timeout=120, **kwargs))

    def download_recording(self, recording_id: str, dest_dir: str) -> str:
        """Download recording content to an mp3 file; returns local path.

        Validates the response so we never save an error body (e.g. a 404/JSON when the
        recording isn't ready yet) as if it were audio — that would fail transcription and
        wrongly flag the call. A raise here lets the worker retry until the audio is ready."""
        os.makedirs(dest_dir, exist_ok=True)
        r = self._get(f"/restapi/v1.0/account/~/recording/{recording_id}/content")
        r.raise_for_status()
        ctype = (r.headers.get("content-type") or "").lower()
        if "audio" not in ctype and "octet-stream" not in ctype and "mpeg" not in ctype:
            raise RuntimeError(f"recording {recording_id} not ready (content-type '{ctype}', "
                               f"{len(r.content)} bytes)")
        if not r.content or len(r.content) < 1024:
            raise RuntimeError(f"recording {recording_id} too small ({len(r.content)} bytes)")
        path = os.path.join(dest_dir, f"rc_{recording_id}.mp3")
        with open(path, "wb") as f:
            f.write(r.content)
        return path

    def setup_subscription(self, webhook_url: str) -> dict:
        """Create the webhook subscription for telephony session events.

        We subscribe to ALL telephony session events (not just ?withRecordings=true) so the
        app hears the call's Disconnected event the moment it ends and can show a placeholder
        immediately, then attach the recording when it later becomes available."""
        r = self._retry_429(lambda: httpx.post(
            f"{self.base}/restapi/v1.0/subscription",
            headers={"Authorization": f"Bearer {self._auth()}"},
            json={
                "eventFilters": [
                    "/restapi/v1.0/account/~/telephony/sessions",
                ],
                "deliveryMode": {"transportType": "WebHook", "address": webhook_url},
                "expiresIn": 630720000,  # max
            },
            timeout=30,
        ))
        return r.json()

    def backfill_call_log(self, days: int = 30) -> list[dict]:
        """Fetch recent recorded calls from the call log for backfill/polling."""
        date_from = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        out, page = [], 1
        while True:
            r = self._get("/restapi/v1.0/account/~/call-log",
                          params={"withRecording": "true", "dateFrom": date_from,
                                  "perPage": 250, "page": page, "view": "Detailed"})
            data = r.json()
            for rec in data.get("records", []):
                if not rec.get("recording"):
                    continue
                out.append({
                    "rc_session_id": rec.get("telephonySessionId") or rec.get("sessionId"),
                    "rc_recording_id": str(rec["recording"]["id"]),
                    "direction": rec.get("direction", "Outbound").lower(),
                    "from_number": (rec.get("from") or {}).get("phoneNumber", ""),
                    "to_number": (rec.get("to") or {}).get("phoneNumber", ""),
                    "started_at": rec.get("startTime"),
                    "duration_sec": rec.get("duration", 0),
                    "extension_id": str(((rec.get("extension") or {}).get("id")) or ""),
                })
            nav = data.get("navigation", {})
            if not nav.get("nextPage"):
                break
            page += 1
        return out


def queue_backfill(db, days: int) -> int:
    """Queue historical recorded calls for processing. Shared by the setup script
    and the admin API endpoint."""
    from datetime import datetime as _dt
    from ..models import Call, User
    rc = RingCentralClient()
    added = 0
    min_secs = settings.min_call_seconds
    for r in rc.backfill_call_log(days):
        if not r["rc_session_id"]:
            continue
        too_short = (r["duration_sec"] or 0) < min_secs
        started = _dt.utcnow()
        if r["started_at"]:
            try:
                started = _dt.fromisoformat(
                    r["started_at"].replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                pass
        existing = db.query(Call).filter(Call.rc_session_id == r["rc_session_id"]).first()
        if existing:
            if too_short:
                # A placeholder for a no-answer / instant-hangup dial — remove it.
                if existing.status in ("awaiting_recording", "no_recording"):
                    db.delete(existing)
                continue
            # Fill in a placeholder created at call-end with the now-available recording.
            if not existing.rc_recording_id and r["rc_recording_id"]:
                existing.rc_recording_id = r["rc_recording_id"]
                existing.started_at = started
                existing.duration_sec = r["duration_sec"] or existing.duration_sec
                if existing.status in ("awaiting_recording", "no_recording"):
                    existing.status, existing.error = "queued", None
                added += 1
            continue
        if too_short:
            continue                                    # don't ingest dead / no-answer dials
        host = (db.query(User).filter(User.rc_extension_id == r["extension_id"]).first()
                if r["extension_id"] else None)
        direction = "outbound" if r["direction"].startswith("out") else "inbound"
        db.add(Call(
            host_id=host.id if host else None,
            direction=direction,
            activity_type=("Outbound - Acquisition" if direction == "outbound"
                           else "Inbound - Call From Customer"),
            from_number=r["from_number"], to_number=r["to_number"],
            started_at=started, duration_sec=r["duration_sec"], status="queued",
            rc_session_id=r["rc_session_id"], rc_recording_id=r["rc_recording_id"],
        ))
        added += 1
    if added:
        db.commit()
    return added
