"""What-works mining + knowledge store + exemplar library (Intelligence Phase 5).

Compares the team's *won* calls against *lost* ones to surface the behaviours that correlate with
closing — then writes them to the KnowledgeEntry store (kind='mined') that the Oracle draws on. Also
auto-nominates the strongest recent calls as exemplars (kind='exemplar') so there's a 'listen to this'
library. Deterministic stats always; Claude phrases the mined patterns (best-effort)."""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy.orm import joinedload

from ...config import settings
from ...models import Call, CallAnalysis, KnowledgeEntry
from .common import _avg_scores, quality_100

log = logging.getLogger("calliq.whatworks")

_MINED_TAG = "__mined__"          # marks auto-generated entries so we can replace them cleanly
WON, LOST = "order_placed", "not_interested"


def _group_stats(db, outcome: str, start, asof) -> dict:
    calls = (db.query(Call).options(joinedload(Call.analysis))
             .filter(Call.status == "completed", Call.outcome == outcome,
                     Call.started_at >= start, Call.started_at < asof).all())
    if not calls:
        return {"n": 0}
    qmap = _avg_scores(db, [c.id for c in calls])
    def _m(vals):
        v = [x for x in vals if x is not None]
        return round(sum(v) / len(v), 1) if v else None
    strengths, improves = Counter(), Counter()
    for c in calls:
        a = c.analysis
        if a:
            for s in (a.strengths or []):
                strengths[s.strip().lower()[:80]] += 1
            for s in (a.improvements or []):
                improves[s.strip().lower()[:80]] += 1
    return {
        "n": len(calls),
        "quality": _m([quality_100(qmap[c.id]) for c in calls if c.id in qmap]),
        "questions": _m([c.analysis.question_rate for c in calls if c.analysis]),
        "talkRatio": _m([c.analysis.talk_ratio for c in calls if c.analysis and c.analysis.talk_ratio]),
        "interruptions": _m([c.analysis.interruptions for c in calls if c.analysis]),
        "lengthMin": _m([round((c.duration_sec or 0) / 60, 1) for c in calls]),
        "topStrengths": [s for s, _ in strengths.most_common(6)],
        "topImprovements": [s for s, _ in improves.most_common(6)],
        "exampleIds": [c.id for c in calls[:6]],
    }


def _template_entries(won: dict, lost: dict) -> list[dict]:
    out = []
    pairs = [("questions", "ask more discovery questions", True),
             ("interruptions", "interrupt less", False),
             ("talkRatio", "let the customer talk more", False)]
    for key, phrase, higher in pairs:
        w, l = won.get(key), lost.get(key)
        if w is None or l is None:
            continue
        better = (w > l) if higher else (w < l)
        if better and abs(w - l) >= (1 if key != "talkRatio" else 4):
            out.append({"title": f"Winners {phrase}",
                        "body": f"On won calls the team averages {w} {key} vs {l} on lost calls. {phrase.capitalize()}.",
                        "tags": [key, "what_works"], "exampleCallIds": won.get("exampleIds", [])[:3]})
    for s in (won.get("topStrengths") or [])[:3]:
        out.append({"title": f"What good sounds like: {s[:48]}", "body": s,
                    "tags": ["exemplar_phrase", "what_works"], "exampleCallIds": won.get("exampleIds", [])[:2]})
    return out


def mine(db, days: int = 90) -> dict:
    """Refresh mined knowledge from won-vs-lost analysis. Replaces previous auto-mined entries."""
    asof = datetime.utcnow()
    start = asof - timedelta(days=days)
    won = _group_stats(db, WON, start, asof)
    lost = _group_stats(db, LOST, start, asof)
    if won.get("n", 0) < 5 or lost.get("n", 0) < 5:
        return {"mined": 0, "reason": "need at least 5 won and 5 lost calls in the window",
                "won": won.get("n", 0), "lost": lost.get("n", 0)}

    entries = []
    if settings.anthropic_api_key:
        from ...pipeline.analyzer import _claude, _extract_json
        system = (
            "You analyse what separates winning sales calls from losing ones at a UK B2B telecoms firm. "
            "From the supplied aggregate stats and recurring phrases, write 3–6 concrete, coachable "
            "'what works' patterns. Each must be grounded in the numbers given (quote them); no invented "
            "figures. UK English. Return STRICT JSON."
        )
        user = ("WON vs LOST stats:\n" + json.dumps({"won": won, "lost": lost}, indent=1, default=str) +
                "\n\nReturn {\"patterns\":[{\"title\":\"…\",\"body\":\"1-2 sentences with the evidence\","
                "\"tags\":[\"…\"]}]}.")
        try:
            data = _extract_json(_claude(system, user, settings.claude_call_model, max_tokens=1600))
            for p in data.get("patterns", []):
                entries.append({"title": p.get("title", "")[:200], "body": p.get("body", ""),
                                "tags": (p.get("tags") or []) + ["what_works"],
                                "exampleCallIds": won.get("exampleIds", [])[:3]})
        except Exception as e:
            log.warning("what-works LLM failed: %s", e)
    if not entries:
        entries = _template_entries(won, lost)

    # replace previous auto-mined entries
    (db.query(KnowledgeEntry)
       .filter(KnowledgeEntry.kind == "mined", KnowledgeEntry.tags.contains([_MINED_TAG]))
       .delete(synchronize_session=False))
    n = 0
    for e in entries:
        ev = [{"type": "call", "callId": cid, "label": "won call"} for cid in e.get("exampleCallIds", [])]
        db.add(KnowledgeEntry(kind="mined", title=e["title"], body=e["body"],
                              tags=(e.get("tags") or []) + [_MINED_TAG], evidence=ev, active=True))
        n += 1
    db.commit()
    return {"mined": n, "won": won["n"], "lost": lost["n"]}


def auto_exemplars(db, days: int = 30, limit: int = 5) -> int:
    """Nominate the strongest recent calls (high quality + a flagged best moment) as exemplars."""
    asof = datetime.utcnow()
    start = asof - timedelta(days=days)
    calls = (db.query(Call).options(joinedload(Call.analysis))
             .filter(Call.status == "completed", Call.started_at >= start).all())
    qmap = _avg_scores(db, [c.id for c in calls])
    cand = []
    for c in calls:
        a = c.analysis
        bm = (a.best_moment if a else None) or {}
        q = quality_100(qmap.get(c.id)) if c.id in qmap else None
        if a and bm.get("quote") and q is not None and q >= 80:
            cand.append((q, c, bm))
    cand.sort(key=lambda x: x[0], reverse=True)
    existing = {e.call_id for e in db.query(KnowledgeEntry).filter(KnowledgeEntry.kind == "exemplar").all()}
    added = 0
    for q, c, bm in cand[:limit]:
        if c.id in existing:
            continue
        rep = (c.host.short_name or c.host.name) if c.host else "Rep"
        db.add(KnowledgeEntry(
            kind="exemplar", title=f"{rep}: {bm.get('reason', 'strong moment')[:80]}",
            body=bm.get("quote", ""), tags=["exemplar"], call_id=c.id,
            start_sec=bm.get("start_sec"), end_sec=bm.get("end_sec"),
            evidence=[{"type": "call", "callId": c.id, "label": f"{rep} · quality {q}"}], active=True))
        added += 1
    if added:
        db.commit()
    return added
