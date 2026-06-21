"""Campaigns API — managers/admin create & manage; everyone can read what's live for them.

A promotion is customer‑facing; an incentive is rep‑facing. Both link to catalogue products and
are time‑bound. Detection of mentions in calls happens in the analyser (Phase 2)."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from ...auth import get_current_user
from ...core import rbac
from ...core.audit import record_audit
from ...db import get_db
from ...models import Call, User
from ...services.salesiq.roles import role_for_user
from .models import INCENTIVE, PROMOTION, TEMPLATES, Campaign, CampaignMention
from .services import live_campaigns, status_of, to_dict

router = APIRouter(prefix="/api/v1/campaigns", tags=["campaigns"])

_WRITE = ("name", "description", "template", "talking_points", "offer", "customer_segments",
          "qualifying_rule", "reward_basis")
_NUM = ("sov_multiplier", "reward_amount", "target_per_rep", "team_target")


def _require_manager(db, user: User):
    if rbac.platform_role(user) == rbac.ADMIN or role_for_user(db, user) == "manager":
        return
    raise HTTPException(403, "Managers or admin only")


def _parse_date(v, field):
    if isinstance(v, date):
        return v
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise HTTPException(400, f"{field} must be YYYY-MM-DD")


def _apply(c: Campaign, body: dict):
    for f in _WRITE:
        key = {"talking_points": "talkingPoints", "customer_segments": "customerSegments",
               "qualifying_rule": "qualifyingRule", "reward_basis": "rewardBasis"}.get(f, f)
        if key in body:
            setattr(c, f, (body[key] or None) if isinstance(body[key], str) else body[key])
    for f, key in (("sov_multiplier", "sovMultiplier"), ("reward_amount", "rewardAmount"),
                   ("target_per_rep", "targetPerRep"), ("team_target", "teamTarget")):
        if key in body:
            v = body[key]
            setattr(c, f, float(v) if v not in (None, "") else None)
    if "teams" in body:
        c.teams = [int(t) for t in (body["teams"] or [])]
    if "productIds" in body:
        c.product_ids = [str(p) for p in (body["productIds"] or [])]
    if "startDate" in body:
        c.start_date = _parse_date(body["startDate"], "startDate")
    if "endDate" in body:
        c.end_date = _parse_date(body["endDate"], "endDate")


@router.get("")
def list_campaigns(status: str | None = None, type: str | None = None, include_archived: bool = False,
                   db=Depends(get_db), user: User = Depends(get_current_user)):
    """All campaigns (managers/admin). Optional status (live|scheduled|expired|archived) / type filter."""
    _require_manager(db, user)
    today = date.today()
    q = db.query(Campaign).filter(Campaign.deleted_at.is_(None))
    if type:
        q = q.filter(Campaign.type == type)
    rows = q.order_by(Campaign.start_date.desc()).all()
    out = [to_dict(c, today) for c in rows]
    if not include_archived:
        out = [d for d in out if not d["archived"]]
    if status:
        out = [d for d in out if d["status"] == status]
    return {"campaigns": out, "templates": TEMPLATES, "types": [PROMOTION, INCENTIVE]}


@router.get("/live")
def my_live(db=Depends(get_db), user: User = Depends(get_current_user)):
    """Live campaigns relevant to the signed‑in user's team (for the Today 'Live now' card)."""
    rows = live_campaigns(db, team_id=user.team_id)
    # reps never see the bonus £; surface the qualifying *product* framing only
    out = []
    for c in rows:
        d = to_dict(c)
        if c.type == INCENTIVE and rbac.platform_role(user) != rbac.ADMIN and role_for_user(db, user) != "manager":
            d.pop("rewardAmount", None)
            d.pop("teamTarget", None)
        out.append(d)
    return {"campaigns": out}


@router.get("/call/{call_id}/mentions")
def call_mentions(call_id: int, db=Depends(get_db), user: User = Depends(get_current_user)):
    """Campaign verdicts for a call — for the badges on the call detail page. The rep on the call,
    or any manager/admin, may see them. Reps never see incentive reward figures."""
    call = db.get(Call, call_id)
    if not call:
        raise HTTPException(404, "Call not found")
    is_mgr = rbac.platform_role(user) == rbac.ADMIN or role_for_user(db, user) == "manager"
    if call.host_id != user.id and not is_mgr:
        raise HTTPException(403, "Not permitted to view this call")
    rows = db.query(CampaignMention).filter(CampaignMention.call_id == call_id).all()
    out = []
    for m in rows:
        c = db.get(Campaign, m.campaign_id)
        if not c or c.deleted_at is not None:
            continue
        out.append({"campaignId": str(c.id), "name": c.name, "type": c.type,
                    "addressed": m.addressed, "evidence": m.evidence,
                    "customerReaction": m.customer_reaction, "outcome": m.outcome,
                    "talkingPoints": c.talking_points})
    return {"mentions": out}


@router.post("/backfill")
def backfill_mentions(body: dict | None = None, db=Depends(get_db), user: User = Depends(get_current_user)):
    """Managers/admin: run campaign detection over recent completed calls missing mentions."""
    _require_manager(db, user)
    days = int((body or {}).get("days", 30))
    from ...services.intelligence.campaign_detect import backfill
    try:
        return backfill(db, days=max(1, min(120, days)))
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Backfill failed: {e}")


@router.get("/attention")
def attention_list(db=Depends(get_db), user: User = Depends(get_current_user)):
    """Live campaigns needing a manager nudge — weak adoption or ending soon (managers/admin)."""
    _require_manager(db, user)
    from .analytics import attention
    return attention(db)


@router.get("/{cid}/performance")
def campaign_perf(cid: str, db=Depends(get_db), user: User = Depends(get_current_user)):
    """Adoption funnel, rep leaderboard, reactions, quality lift + snippets (managers/admin)."""
    _require_manager(db, user)
    c = db.get(Campaign, cid)
    if not c or c.deleted_at is not None:
        raise HTTPException(404, "Campaign not found")
    from .analytics import campaign_performance
    return campaign_performance(db, c)


@router.get("/{cid}/closeout")
def campaign_closeout(cid: str, db=Depends(get_db), user: User = Depends(get_current_user)):
    """AI close-out / ROI report for a campaign (managers/admin)."""
    _require_manager(db, user)
    c = db.get(Campaign, cid)
    if not c or c.deleted_at is not None:
        raise HTTPException(404, "Campaign not found")
    from .closeout import closeout_report
    return closeout_report(db, c)


@router.get("/{cid}")
def get_campaign(cid: str, db=Depends(get_db), user: User = Depends(get_current_user)):
    _require_manager(db, user)
    c = db.get(Campaign, cid)
    if not c or c.deleted_at is not None:
        raise HTTPException(404, "Campaign not found")
    return to_dict(c)


@router.post("")
def create_campaign(body: dict, request: Request, db=Depends(get_db), user: User = Depends(get_current_user)):
    _require_manager(db, user)
    ctype = (body.get("type") or "").strip().lower()
    if ctype not in (PROMOTION, INCENTIVE):
        raise HTTPException(400, "type must be 'promotion' or 'incentive'")
    if not (body.get("name") or "").strip():
        raise HTTPException(400, "Name is required")
    if "startDate" not in body or "endDate" not in body:
        raise HTTPException(400, "startDate and endDate are required")
    c = Campaign(type=ctype, name=body["name"].strip(), created_by_id=user.id,
                 teams=[], product_ids=[], start_date=date.today(), end_date=date.today())
    _apply(c, body)
    if c.end_date < c.start_date:
        raise HTTPException(400, "endDate cannot be before startDate")
    db.add(c)
    db.flush()
    record_audit(db, actor=user, action="CREATE", entity_type="campaign", entity_id=None,
                 field="name", new=c.name, request=request)
    db.commit()
    return to_dict(c)


@router.patch("/{cid}")
def update_campaign(cid: str, body: dict, request: Request, db=Depends(get_db), user: User = Depends(get_current_user)):
    _require_manager(db, user)
    c = db.get(Campaign, cid)
    if not c or c.deleted_at is not None:
        raise HTTPException(404, "Campaign not found")
    if "archived" in body:
        c.archived = bool(body["archived"])
    _apply(c, body)
    if c.end_date < c.start_date:
        raise HTTPException(400, "endDate cannot be before startDate")
    record_audit(db, actor=user, action="UPDATE", entity_type="campaign", entity_id=None,
                 field="name", new=c.name, request=request)
    db.commit()
    return to_dict(c)


@router.delete("/{cid}")
def delete_campaign(cid: str, request: Request, db=Depends(get_db), user: User = Depends(get_current_user)):
    """Soft‑delete (managers/admin). Prefer archiving (PATCH archived=true) to keep history."""
    _require_manager(db, user)
    c = db.get(Campaign, cid)
    if not c:
        raise HTTPException(404, "Campaign not found")
    c.deleted_at = datetime.utcnow()
    record_audit(db, actor=user, action="DELETE", entity_type="campaign", entity_id=None,
                 field="name", old=c.name, request=request)
    db.commit()
    return {"ok": True}
