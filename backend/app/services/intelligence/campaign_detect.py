"""Campaign-aware analysis (Roadmap Phase 2).

After a call is analysed, check it against the campaigns that were live for that rep's team on the
call date and record, per campaign, whether the rep introduced it (promotion) / pitched the
qualifying product (incentive), how the customer reacted, and the likely outcome. One focused Claude
pass, fully isolated from the main analyzer so a detection error never breaks call processing.

Reps are never told the bonus £ — incentive detection only looks at whether the qualifying *product*
was pitched.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from ...modules.campaigns.models import INCENTIVE, PROMOTION, Campaign, CampaignMention
from ...modules.campaigns.services import live_campaigns
from ...modules.catalog.models import Product
from ...pipeline.analyzer import _claude, _extract_json, _format_transcript
from ...config import settings

log = logging.getLogger("calliq.campaigns")

_REACTIONS = {"positive", "neutral", "objection", "n/a"}
_ADDRESSED = {"yes", "weak", "missed"}


def _product_names(db: Session, ids: list[str]) -> list[str]:
    if not ids:
        return []
    rows = db.query(Product).filter(Product.id.in_(ids)).all()
    return [p.name for p in rows]


def _campaign_brief(db: Session, c: Campaign) -> dict:
    """What the detector needs to know — never the bonus £ (kept out of the model context entirely)."""
    prods = _product_names(db, c.product_ids or [])
    if c.type == PROMOTION:
        goal = ("Did the rep INTRODUCE this promotion to the customer (mention the offer/deal)?")
        detail = c.offer or c.description or ""
    else:
        goal = ("Did the rep PITCH the qualifying product below (the thing that makes a sale count)? "
                "Do NOT consider any bonus — only whether the product was genuinely pitched.")
        detail = c.qualifying_rule or c.description or ""
    return {"campaign_id": str(c.id), "type": c.type, "name": c.name,
            "products": prods, "what_to_check": goal, "detail": detail,
            "talking_points": c.talking_points or ""}


def _detect(turns: list[dict], rep_name: str, briefs: list[dict]) -> list[dict]:
    transcript = _format_transcript(turns, rep_name)
    system = (
        "You are a sales-call campaign auditor for BT Local Business Oxford & Bucks (UK telecom). "
        "For each campaign you are given, judge from the transcript whether the rep addressed it, "
        "how the customer reacted, and the likely outcome. Return STRICT JSON only. UK English. "
        "Be conservative: only mark 'yes' when the rep clearly raised it; 'weak' if barely/poorly; "
        "'missed' if not at all. Never invent moments."
    )
    user = f"""CAMPAIGNS that were live on this call (judge each one):
{json.dumps(briefs, indent=1)}

TRANSCRIPT (mm:ss; Rep is {rep_name}):
{transcript}

Return JSON exactly:
{{"mentions": [
  {{"campaign_id": "<id>",
    "addressed": "yes|weak|missed",
    "evidence": "one short sentence: what the rep said (or note it was never raised)",
    "customer_reaction": "positive|neutral|objection|n/a",
    "outcome": "short phrase e.g. 'interested — wants a quote' | 'not now' | 'ordered' | 'no reaction' "
  }}
]}}
Include exactly one entry per campaign listed."""
    raw = _claude(system, user, settings.claude_call_model, max_tokens=1500)
    data = _extract_json(raw)
    return data.get("mentions", []) if isinstance(data, dict) else []


def detect_for_call(db: Session, call, turns: list[dict], rep_name: str) -> int:
    """Detect + persist campaign mentions for one analysed call. Returns rows written.
    Safe to call repeatedly — it replaces any existing mentions for the call."""
    on_date = call.started_at.date() if call.started_at else None
    team_id = call.host.team_id if call.host else None
    camps = live_campaigns(db, team_id=team_id, on_date=on_date)
    # Always clear stale rows first (e.g. a campaign was edited/removed).
    db.query(CampaignMention).filter(CampaignMention.call_id == call.id).delete()
    if not camps:
        return 0
    briefs = [_campaign_brief(db, c) for c in camps]
    by_id = {str(c.id): c for c in camps}
    try:
        verdicts = _detect(turns, rep_name, briefs)
    except Exception as e:  # never break the pipeline
        log.warning("campaign detection failed for call %s: %s", call.id, e)
        return 0
    written = 0
    for v in verdicts:
        cid = str(v.get("campaign_id", ""))
        if cid not in by_id:
            continue
        addressed = (v.get("addressed") or "missed").lower()
        if addressed not in _ADDRESSED:
            addressed = "missed"
        reaction = (v.get("customer_reaction") or "n/a").lower()
        if reaction not in _REACTIONS:
            reaction = "n/a"
        db.add(CampaignMention(
            campaign_id=cid, call_id=call.id, host_id=call.host_id,
            call_date=on_date, addressed=addressed,
            evidence=(v.get("evidence") or "")[:1000],
            customer_reaction=reaction, outcome=(v.get("outcome") or "")[:120],
        ))
        written += 1
    return written


def backfill(db: Session, days: int = 30, limit: int = 500) -> dict:
    """Run detection over recently-completed calls that have no mentions yet (manager-triggered)."""
    from datetime import datetime, timedelta
    from ...models import Call, TranscriptTurn

    if not live_campaigns(db):  # nothing live recently → nothing to do
        # still allow per-date matching for calls inside campaign windows
        pass
    cutoff = datetime.utcnow() - timedelta(days=days)
    q = (db.query(Call)
         .filter(Call.status == "completed", Call.started_at >= cutoff)
         .order_by(Call.started_at.desc()).limit(limit))
    done = scanned = 0
    for call in q.all():
        existing = db.query(CampaignMention.id).filter(CampaignMention.call_id == call.id).first()
        if existing:
            continue
        turns_rows = (db.query(TranscriptTurn).filter(TranscriptTurn.call_id == call.id)
                      .order_by(TranscriptTurn.start_sec).all())
        if not turns_rows:
            continue
        turns = [{"speaker": t.speaker, "start_sec": t.start_sec, "end_sec": t.end_sec, "text": t.text}
                 for t in turns_rows]
        rep_name = call.host.name if call.host else "Rep"
        scanned += 1
        if detect_for_call(db, call, turns, rep_name):
            done += 1
        db.commit()
    return {"scanned": scanned, "withMentions": done}
