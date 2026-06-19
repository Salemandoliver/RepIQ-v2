"""End-to-end API tests against an in-memory SQLite DB with the demo seed."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "sqlite:///./test_calliq.db"
os.environ["DEMO_MODE"] = "true"

import pytest
from fastapi.testclient import TestClient

for f in ("test_calliq.db",):
    if os.path.exists(f):
        os.remove(f)

from app.main import app, startup  # noqa: E402

startup()  # TestClient without a context manager doesn't fire startup events
client = TestClient(app)


@pytest.fixture(scope="session")
def token():
    r = client.post("/api/auth/login",
                    json={"email": "admin@btlocalbusiness.co.uk", "password": "demo1234"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_health():
    assert client.get("/api/health").json()["ok"] is True


def test_login_rejects_bad_password():
    r = client.post("/api/auth/login",
                    json={"email": "admin@btlocalbusiness.co.uk", "password": "wrong"})
    assert r.status_code == 401


def test_calls_require_auth():
    assert client.get("/api/calls").status_code == 401


def test_list_calls(token):
    r = client.get("/api/calls?page_size=10", headers=auth(token))
    assert r.status_code == 200
    data = r.json()
    assert data["total"] > 100
    item = data["items"][0]
    assert {"id", "activity_type", "duration_sec", "host"} <= item.keys()


def test_filters(token):
    r = client.get("/api/calls?activity_type=Outbound - Acquisition&min_minutes=1",
                   headers=auth(token))
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert item["activity_type"] == "Outbound - Acquisition"
        assert item["duration_sec"] >= 60


def test_transcript_search(token):
    r = client.get("/api/calls?transcript=broadband&said_by=rep", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["total"] > 0


def test_call_detail_has_analysis_and_scores(token):
    r = client.get("/api/calls?activity_type=Outbound - Acquisition&page_size=1",
                   headers=auth(token))
    call_id = r.json()["items"][0]["id"]
    d = client.get(f"/api/calls/{call_id}", headers=auth(token)).json()
    assert d["analysis"] is not None
    assert len(d["turns"]) > 0
    assert len(d["scores"]) > 0
    crit = d["scores"][0]["criteria"][0]
    assert {"name", "score", "feedback", "evidence"} <= crit.keys()


def test_score_filter(token):
    r = client.get("/api/calls?min_score=4", headers=auth(token))
    for item in r.json()["items"]:
        assert item["overall_score"] >= 4


def test_listen_and_comment(token):
    call_id = client.get("/api/calls?page_size=1", headers=auth(token)).json()["items"][0]["id"]
    r = client.post(f"/api/calls/{call_id}/listen", headers=auth(token))
    assert r.json()["ok"]
    r = client.post(f"/api/calls/{call_id}/comments",
                    json={"body": "Nice call", "at_sec": 12.5}, headers=auth(token))
    assert r.status_code == 200
    assert client.get(f"/api/calls/{call_id}/comments", headers=auth(token)).json()


def test_trending_and_live_feed(token):
    assert client.get("/api/calls/trending", headers=auth(token)).status_code == 200
    feed = client.get("/api/calls/live-feed", headers=auth(token)).json()
    assert len(feed) > 0


def test_insights(token):
    a = client.get("/api/insights/activity?days=90", headers=auth(token)).json()
    assert a["totals"]["outbound"] > 0 and len(a["series"]) > 80
    e = client.get("/api/insights/engagement?days=90", headers=auth(token)).json()
    assert e["overall"]["talk_ratio"] > 0 and len(e["reps"]) > 5
    t = client.get("/api/insights/topics?days=90", headers=auth(token)).json()
    assert any(x["percentage"] > 0 for x in t)
    s = client.get("/api/insights/scores?days=90", headers=auth(token)).json()
    assert len(s["reps"]) > 5 and len(s["criteria"]) > 0
    c = client.get("/api/insights/coaching?days=90", headers=auth(token)).json()
    assert c["total"] > 0


def test_admin_crud(token):
    h = auth(token)
    r = client.post("/api/admin/topics", headers=h,
                    json={"name": "Cloud Voice", "keywords": ["cloud voice", "voip"],
                          "color": "#3b82f6"})
    assert r.status_code == 200
    tid = r.json()["id"]
    assert client.delete(f"/api/admin/topics/{tid}", headers=h).json()["ok"]

    r = client.post("/api/admin/users", headers=h,
                    json={"name": "Test Rep", "email": "test.rep@btlocalbusiness.co.uk",
                          "password": "pass1234"})
    assert r.status_code == 200
    uid = r.json()["id"]
    r = client.patch(f"/api/admin/users/{uid}", headers=h, json={"active": False})
    assert r.json()["active"] is False


def test_non_admin_cannot_admin():
    r = client.post("/api/auth/login",
                    json={"email": "alex.bain@btlocalbusiness.co.uk", "password": "demo1234"})
    tok = r.json()["access_token"]
    r = client.post("/api/admin/topics", headers=auth(tok),
                    json={"name": "X", "keywords": [], "color": "#000000"})
    assert r.status_code == 403


def test_reports(token):
    r = client.get("/api/reports", headers=auth(token))
    assert r.status_code == 200 and len(r.json()) > 0
    rep = client.get(f"/api/reports/{r.json()[0]['id']}", headers=auth(token)).json()
    assert "Coaching" in rep["name"]
    g = client.post("/api/reports/generate?days=7", headers=auth(token))
    assert g.status_code == 200 and g.json()["content_md"]


def test_metrics_computation():
    from app.pipeline.metrics import compute_metrics
    turns = [
        {"speaker": "rep", "start_sec": 0, "end_sec": 10, "text": "Hello there? How are you?"},
        {"speaker": "customer", "start_sec": 11, "end_sec": 20, "text": "Good thanks."},
        {"speaker": "rep", "start_sec": 22, "end_sec": 30, "text": "Great. Tell me about your business?"},
    ]
    m = compute_metrics(turns)
    assert 0 < m["talk_ratio"] < 100
    assert m["question_rate"] == 3
    assert m["patience_sec"] == 2.0


def test_role_assignment():
    from app.pipeline.transcriber import assign_roles
    turns = [
        {"speaker_idx": 0, "start_sec": 0, "end_sec": 30,
         "text": "Long talker asking questions? More questions?"},
        {"speaker_idx": 1, "start_sec": 31, "end_sec": 35, "text": "Short answer."},
    ]
    roles = assign_roles(turns)
    assert roles[0]["speaker"] == "rep" and roles[1]["speaker"] == "customer"


def test_ask_presets_seeded(token):
    r = client.get("/api/calls/ask-presets", headers=auth(token))
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert "Deal blockers" in names and "SPIN check" in names


def test_ask_requires_ai_key(token):
    call_id = client.get("/api/calls?page_size=1", headers=auth(token)).json()["items"][0]["id"]
    r = client.post(f"/api/calls/{call_id}/ask", json={"question": "Will they sign?"},
                    headers=auth(token))
    assert r.status_code == 503  # no Anthropic key in test env


def test_ask_preset_admin_crud(token):
    h = auth(token)
    r = client.post("/api/admin/ask-presets", headers=h,
                    json={"name": "Test Q", "prompt": "What was discussed?"})
    assert r.status_code == 200
    pid = r.json()["id"]
    r = client.patch(f"/api/admin/ask-presets/{pid}", headers=h, json={"name": "Test Q2"})
    assert r.json()["name"] == "Test Q2"
    assert client.delete(f"/api/admin/ask-presets/{pid}", headers=h).json()["ok"]


def test_contact_call_counts(token):
    h = auth(token)
    item = client.get("/api/calls?page_size=5", headers=h).json()["items"][0]
    assert item.get("contact_calls") is not None and item["contact_calls"] >= 1
    d = client.get(f"/api/calls/{item['id']}", headers=h).json()
    assert d["contact_calls"] >= 1


def test_playlists(token):
    h = auth(token)
    r = client.post("/api/playlists", json={"name": "Best SPIN calls",
                                            "description": "Exemplary discovery"}, headers=h)
    assert r.status_code == 200
    pid = r.json()["id"]
    call_id = client.get("/api/calls?page_size=1", headers=h).json()["items"][0]["id"]
    assert client.post(f"/api/playlists/{pid}/items", json={"call_id": call_id}, headers=h).json()["ok"]
    assert client.post(f"/api/playlists/{pid}/items", json={"call_id": call_id}, headers=h).json().get("duplicate")
    d = client.get(f"/api/playlists/{pid}", headers=h).json()
    assert d["tracks"] == 1 and d["items"][0]["call"]["id"] == call_id
    assert client.delete(f"/api/playlists/{pid}/items/{call_id}", headers=h).json()["ok"]
    assert client.delete(f"/api/playlists/{pid}", headers=h).json()["ok"]


def test_gdpr_erase(token):
    h = auth(token)
    item = client.get("/api/calls?page_size=1", headers=h).json()["items"][0]
    from urllib.parse import quote
    r = client.delete(f"/api/admin/gdpr/erase?phone={quote(item['to_number'])}", headers=h)
    assert r.json()["erased_calls"] >= 1
    assert client.get(f"/api/calls/{item['id']}", headers=h).status_code == 404
