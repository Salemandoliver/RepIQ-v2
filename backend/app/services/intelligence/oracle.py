"""The Org Oracle (Intelligence Phase 5).

A manager-scoped, org-wide Ask that reasons across the whole sales floor: who's strongest at a given
skill, what's working on a product, draft a hiring scorecard from the top performers' patterns, who
should mentor whom. It assembles context from the facts RepIQ already has — the per-rep skill table,
live insights, mined knowledge/exemplars, and the most relevant call evidence (semantic when
embeddings are configured, keyword otherwise) — then lets Claude reason over it.

Distinct from the day-to-day Ask co-pilot: the oracle is cross-rep and pattern-seeking. Managers/admin
only (it sees the whole team)."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta

from ...config import settings
from ...models import Call, CallAnalysis, KnowledgeEntry, User
from .common import rep_averages, team_averages

log = logging.getLogger("calliq.oracle")

_STOP = set("the a an and or of to for in on with is are was were be been what who which how why "
            "when where do does did our we us your you their them best most who's whats what's at by "
            "from about into over per vs versus team rep reps call calls".split())


def _skill_table(db, days: int = 60) -> list[dict]:
    """Compact per-rep skill snapshot so the oracle can answer 'who's best at X'."""
    from .benchmarks import league
    out = []
    for r in league(db, days=days)["reps"][:25]:
        a = rep_averages(db, r["userId"], days=days)
        out.append({"name": r["name"], "group": r.get("group"), "quality": r.get("quality"),
                    "orders": r.get("orders"), "questions": a.get("questions"),
                    "talkRatio": a.get("talk_ratio"), "interruptions": a.get("interruptions"),
                    "closeRate": a.get("closeRate"), "calls": a.get("calls")})
    return out


def _keyword_calls(db, question: str, k: int) -> list[int]:
    toks = [t for t in re.findall(r"[a-z]+", question.lower()) if t not in _STOP and len(t) > 2]
    if not toks:
        return []
    cutoff = datetime.utcnow() - timedelta(days=120)
    rows = (db.query(Call.id, CallAnalysis)
            .join(CallAnalysis, CallAnalysis.call_id == Call.id)
            .filter(Call.started_at >= cutoff).limit(400).all())
    scored = []
    for cid, a in rows:
        hay = " ".join([a.summary_intro or ""] + (a.summary_points or [])
                       + (a.strengths or []) + (a.improvements or [])).lower()
        score = sum(hay.count(t) for t in toks)
        if score:
            scored.append((score, cid))
    scored.sort(reverse=True)
    return [cid for _, cid in scored[:k]]


def _relevant_calls(db, question: str, k: int = 6) -> list[dict]:
    from .memory import search
    ids = [r["callId"] for r in search(db, question, k=k)] or _keyword_calls(db, question, k)
    out = []
    for cid in ids:
        c = db.get(Call, cid)
        if not c:
            continue
        a = c.analysis
        out.append({
            "callId": cid,
            "rep": (c.host.short_name or c.host.name) if c.host else None,
            "date": c.started_at.strftime("%d/%m/%Y") if c.started_at else None,
            "customer": c.customer_company or c.customer_name,
            "outcome": c.outcome,
            "summary": (a.summary_intro if a else "") or "",
            "strengths": (a.strengths or [])[:3] if a else [],
        })
    return out


def _knowledge(db) -> list[dict]:
    rows = (db.query(KnowledgeEntry).filter(KnowledgeEntry.active.is_(True))
            .order_by(KnowledgeEntry.pinned.desc(), KnowledgeEntry.created_at.desc()).limit(30).all())
    return [{"kind": r.kind, "title": r.title, "body": r.body, "tags": r.tags or []} for r in rows]


def _insights_digest(db) -> list[dict]:
    from ...models import Insight
    rows = (db.query(Insight).filter(Insight.status.in_(("new", "acknowledged")))
            .order_by(Insight.updated_at.desc()).limit(40).all())
    return [{"scope": i.scope, "subject": i.subject_name, "category": i.category,
             "severity": i.severity, "title": i.title} for i in rows]


def _forecast_digest(db) -> dict | None:
    """Team weekly-forecast standing for the Oracle — so managers can ask about reliability,
    sandbagging, who's behind, etc."""
    try:
        from ...modules.forecast import services as _fc
        ts = _fc.team_summary(db)
        return {
            "week": ts["week"], "teamAchievementPct": ts["pct"],
            "missingForecast": ts["missing"], "behindPace": ts["behind"],
            "reps": [{"name": s["name"], "reliabilityScore": s["reliabilityScore"],
                      "weeksTracked": s["weeks"], "hits": s["hitCount"], "thisWeekPct": s["thisWeekPct"],
                      "summary": s["summary"],
                      "flags": [k for k in ("chronicMiss", "strong", "sandbagger", "notSubmitted") if s.get(k)]}
                     for s in ts["signals"]],
        }
    except Exception:
        return None


def ask_oracle(db, user: User, question: str, days: int = 60) -> dict:
    if not settings.anthropic_api_key:
        return {"answer": "The Oracle needs the Anthropic API key configured to reason over the data.",
                "sources": []}
    calls = _relevant_calls(db, question)
    context = {
        "skillTable": _skill_table(db, days=days),
        "teamAverages": team_averages(db, days=days),
        "openInsights": _insights_digest(db),
        "knowledge": _knowledge(db),
        "weeklyForecast": _forecast_digest(db),
        "relevantCalls": calls,
    }
    from ...pipeline.analyzer import _claude
    system = (
        "You are the RepIQ Oracle — the analytical brain of a UK B2B telecoms sales floor (BT Local "
        "Business Oxford & Bucks). A SALES MANAGER is asking. Reason across the whole team using ONLY "
        "the supplied data: the per-rep skill table, team averages, live insights, mined knowledge, and "
        "the most relevant recent calls. Name specific reps and cite call dates/customers as evidence. "
        "If asked to draft something (e.g. a hiring scorecard, a coaching plan), ground it in the "
        "patterns visible in the data. Never invent numbers or names not present. If the data can't "
        "support an answer, say what's missing. Be concise, concrete and structured. UK English."
    )
    user_msg = f"MANAGER QUESTION: {question}\n\nDATA:\n{json.dumps(context, indent=1, default=str)}"
    try:
        answer = _claude(system, user_msg, settings.claude_call_model, max_tokens=1600)
    except Exception as e:
        log.exception("oracle failed")
        return {"answer": f"The Oracle hit an error: {e}", "sources": []}
    sources = [{"type": "call", "callId": c["callId"],
                "label": f"{c['rep'] or 'Rep'} · {c['customer'] or 'call'} · {c['date'] or ''}"}
               for c in calls]
    from ...core import embeddings as _emb
    return {"answer": answer, "sources": sources, "semantic": _emb.configured()}
