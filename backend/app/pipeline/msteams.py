"""Microsoft Teams meeting ingestion via Microsoft Graph.

Teams saves meeting recordings to the organiser's OneDrive "Recordings" folder.
The worker polls every tenant user's Recordings folder for new .mp4 files and
queues them as 'Teams Meeting' calls; the normal pipeline (Deepgram + Claude)
then transcribes and scores them.

Rep mapping: tenant emails (e.g. name@synvestment.co.uk) are matched to CallIQ
users by the local part of the email (name@btlocalbusiness.co.uk).
Dedup key: Call.rc_session_id = "ms:<driveItemId>".
Re-download ref: Call.rc_recording_id = "ms:<userId>:<driveItemId>".
"""
import logging
import os
import re
from datetime import datetime, timedelta, timezone

import httpx

from ..config import settings

log = logging.getLogger("calliq.msteams")
GRAPH = "https://graph.microsoft.com/v1.0"


class GraphClient:
    def __init__(self):
        self._token: str | None = None
        self._expiry = datetime.min

    def _auth(self) -> str:
        if self._token and datetime.utcnow() < self._expiry:
            return self._token
        r = httpx.post(
            f"https://login.microsoftonline.com/{settings.ms_tenant_id}/oauth2/v2.0/token",
            data={"grant_type": "client_credentials",
                  "client_id": settings.ms_client_id,
                  "client_secret": settings.ms_client_secret,
                  "scope": "https://graph.microsoft.com/.default"},
            timeout=30)
        r.raise_for_status()
        data = r.json()
        self._token = data["access_token"]
        self._expiry = datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600) - 60)
        return self._token

    def get(self, path: str, **kwargs) -> httpx.Response:
        return httpx.get(f"{GRAPH}{path}",
                         headers={"Authorization": f"Bearer {self._auth()}"},
                         timeout=120, **kwargs)

    def users(self) -> list[dict]:
        out, url = [], "/users?$top=999&$select=id,displayName,mail,userPrincipalName"
        while url:
            r = self.get(url)
            r.raise_for_status()
            data = r.json()
            out += data.get("value", [])
            nxt = data.get("@odata.nextLink", "")
            url = nxt.replace(GRAPH, "") if nxt else None
        return out

    def recordings(self, user_id: str, since: datetime) -> list[dict]:
        """New .mp4 recordings in a user's OneDrive Recordings folder."""
        r = self.get(f"/users/{user_id}/drive/root:/Recordings:/children?$top=200")
        if r.status_code in (400, 404, 423):  # no drive / no Recordings folder / locked drive
            return []
        r.raise_for_status()
        out = []
        for it in r.json().get("value", []):
            if not it.get("name", "").lower().endswith(".mp4"):
                continue
            created = datetime.fromisoformat(
                it["createdDateTime"].replace("Z", "+00:00"))
            if created >= since.replace(tzinfo=timezone.utc):
                out.append(it)
        return out

    def download(self, user_id: str, item_id: str, dest_dir: str) -> str:
        os.makedirs(dest_dir, exist_ok=True)
        r = self.get(f"/users/{user_id}/drive/items/{item_id}/content")
        # Graph redirects to a pre-signed URL; httpx follows when allowed
        if r.status_code in (301, 302):
            r = httpx.get(r.headers["Location"], timeout=600)
        r.raise_for_status()
        path = os.path.join(dest_dir, f"ms_{item_id}.mp4")
        with open(path, "wb") as f:
            f.write(r.content)
        return path


_graph: GraphClient | None = None


def shared_graph() -> GraphClient:
    global _graph
    if _graph is None:
        _graph = GraphClient()
    return _graph


def _meeting_title(filename: str) -> str:
    """'BT Teams Meeting with Stephanie-20260612_141918-Meeting Recording.mp4' → clean title."""
    name = re.sub(r"\.mp4$", "", filename, flags=re.I)
    name = re.sub(r"-\d{8}_\d{6}-Meeting Recording.*$", "", name)
    name = re.sub(r"-Meeting Recording.*$", "", name)
    return name.strip() or "Teams Meeting"


def poll_teams_recordings(db) -> int:
    """Scan all tenant users' Recordings folders and queue new meetings."""
    from ..models import Call, User
    g = shared_graph()
    since = datetime.utcnow() - timedelta(days=settings.ms_lookback_days)

    # Map tenant users to CallIQ users by email local part
    calliq_users = {u.email.split("@")[0].lower(): u for u in db.query(User).all()}

    added = 0
    for tu in g.users():
        email = (tu.get("mail") or tu.get("userPrincipalName") or "").lower()
        try:
            items = g.recordings(tu["id"], since)
        except Exception as e:
            log.warning("Recordings scan failed for %s: %s", email, str(e)[:120])
            continue
        if not items:
            continue
        host = calliq_users.get(email.split("@")[0]) if email else None
        for it in items:
            key = f"ms:{it['id']}"
            if db.query(Call).filter(Call.rc_session_id == key).first():
                continue
            created = datetime.fromisoformat(
                it["createdDateTime"].replace("Z", "+00:00")).replace(tzinfo=None)
            try:
                audio_path = g.download(tu["id"], it["id"], settings.audio_dir)
            except Exception as e:
                log.warning("Download failed for %s: %s", it.get("name"), str(e)[:120])
                continue
            db.add(Call(
                host_id=host.id if host else None,
                direction="outbound",
                activity_type="Teams Meeting",
                from_number="", to_number="",
                customer_name=_meeting_title(it.get("name", "")),
                started_at=created,
                duration_sec=0,
                status="queued",
                audio_path=audio_path,
                rc_session_id=key,
                rc_recording_id=f"ms:{tu['id']}:{it['id']}",
            ))
            added += 1
    if added:
        db.commit()
        log.info("Teams poller queued %d new meetings", added)
    return added


def redownload(ref: str, dest_dir: str) -> str:
    """Re-fetch a Teams recording from 'ms:<userId>:<itemId>'."""
    _, user_id, item_id = ref.split(":", 2)
    return shared_graph().download(user_id, item_id, dest_dir)
