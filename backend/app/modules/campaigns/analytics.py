"""Per-campaign performance (Roadmap Phase 3).

Turns the CampaignMention rows + call scores into an adoption funnel, a rep leaderboard, customer-
reaction mix, a quality comparison (addressed vs missed), and example snippets. For incentives it adds
a pitch-adoption + outcome read (Sales Tracker payout reconciliation is layered on separately).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from datetime import date

from ...models import Call, User
from .models import Campaign, CampaignMention
from .services import live_campaigns, status_of


def _disp(u: User | None) -> str:
    if not u:
        return "Unknown"
    return u.short_name or u.name


def _overall(call: Call) -> float | None:
    if not call.scores:
        return None
    return round(sum(s.overall for s in call.scores) / len(call.scores), 1)


def _mean(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 1) if xs else None


def attention(db: Session) -> dict:
    """Live campaigns that need a manager nudge (Roadmap Phase 4 alerts) — weak adoption or ending
    soon. Cheap: one mention query per live campaign, counts only."""
    today = date.today()
    items = []
    for c in live_campaigns(db):
        rows = db.query(CampaignMention.addressed).filter(CampaignMention.campaign_id == str(c.id)).all()
        total = len(rows)
        yes = sum(1 for (a,) in rows if a == "yes")
        rate = round(100 * yes / total) if total else None
        days_left = (c.end_date - today).days
        flags = []
        if total >= 5 and rate is not None and rate < 50:
            flags.append(f"low adoption ({rate}%)")
        if days_left <= 3:
            flags.append(f"ends in {days_left}d" if days_left > 0 else "ends today")
        if total == 0 and (today - c.start_date).days >= 3:
            flags.append("no calls tracked yet")
        if flags:
            items.append({"id": str(c.id), "name": c.name, "type": c.type,
                          "rate": rate, "calls": total, "daysLeft": days_left, "flags": flags})
    items.sort(key=lambda x: (x["daysLeft"], x["rate"] if x["rate"] is not None else 0))
    return {"items": items}


def campaign_performance(db: Session, c: Campaign) -> dict:
    mentions = db.query(CampaignMention).filter(CampaignMention.campaign_id == str(c.id)).all()
    total = len(mentions)
    counts = {"yes": 0, "weak": 0, "missed": 0}
    reactions = {"positive": 0, "neutral": 0, "objection": 0}
    by_rep: dict[int, dict] = {}
    call_ids = []

    for m in mentions:
        counts[m.addressed if m.addressed in counts else "missed"] += 1
        if m.addressed in ("yes", "weak") and m.customer_reaction in reactions:
            reactions[m.customer_reaction] += 1
        if m.host_id is not None:
            r = by_rep.setdefault(m.host_id, {"total": 0, "yes": 0, "weak": 0, "missed": 0})
            r["total"] += 1
            r[m.addressed if m.addressed in r else "missed"] += 1
        if m.call_id:
            call_ids.append(m.call_id)

    addressed = counts["yes"] + counts["weak"]
    adoption_rate = round(100 * counts["yes"] / total) if total else None
    reach_rate = round(100 * addressed / total) if total else None

    # quality: addressed (yes/weak) vs missed
    calls = {c2.id: c2 for c2 in db.query(Call).filter(Call.id.in_(call_ids)).all()} if call_ids else {}
    q_addr, q_miss = [], []
    for m in mentions:
        call = calls.get(m.call_id)
        if not call:
            continue
        q = _overall(call)
        (q_addr if m.addressed in ("yes", "weak") else q_miss).append(q)

    # rep leaderboard
    users = {u.id: u for u in db.query(User).filter(User.id.in_(list(by_rep.keys()))).all()} if by_rep else {}
    leaderboard = []
    for hid, r in by_rep.items():
        rate = round(100 * r["yes"] / r["total"]) if r["total"] else 0
        leaderboard.append({"userId": hid, "name": _disp(users.get(hid)),
                            "addressed": r["yes"], "weak": r["weak"], "missed": r["missed"],
                            "total": r["total"], "rate": rate})
    leaderboard.sort(key=lambda x: (-x["rate"], -x["total"]))

    # snippets — wins (addressed + positive) and a couple of misses worth coaching
    wins, misses = [], []
    for m in mentions:
        rep = _disp(users.get(m.host_id)) if m.host_id in users else None
        if m.addressed == "yes" and m.customer_reaction == "positive" and m.evidence and len(wins) < 4:
            wins.append({"rep": rep, "callId": m.call_id, "evidence": m.evidence, "outcome": m.outcome})
        elif m.addressed == "missed" and len(misses) < 4:
            misses.append({"rep": rep, "callId": m.call_id, "outcome": m.outcome})

    out = {
        "id": str(c.id), "name": c.name, "type": c.type, "status": status_of(c),
        "startDate": c.start_date.isoformat(), "endDate": c.end_date.isoformat(),
        "totals": {"calls": total, "addressed": counts["yes"], "weak": counts["weak"],
                   "missed": counts["missed"], "reach": addressed},
        "adoptionRate": adoption_rate, "reachRate": reach_rate,
        "reactions": reactions,
        "quality": {"addressed": _mean(q_addr), "missed": _mean(q_miss),
                    "lift": (round(_mean(q_addr) - _mean(q_miss), 1)
                             if _mean(q_addr) is not None and _mean(q_miss) is not None else None)},
        "leaderboard": leaderboard,
        "snippets": {"wins": wins, "misses": misses},
    }

    if c.type == "incentive":
        # Rep-facing read: how many qualifying conversations + how they landed. (Bonus £ stays
        # manager-only; Sales-Tracker order reconciliation handled separately.)
        ordered = sum(1 for m in mentions if (m.outcome or "").lower().find("order") >= 0)
        positive = reactions["positive"]
        out["incentive"] = {
            "pitched": counts["yes"], "weakPitch": counts["weak"], "missed": counts["missed"],
            "positiveReactions": positive, "likelyOrders": ordered,
            "targetPerRep": c.target_per_rep, "teamTarget": c.team_target,
            "rewardAmount": c.reward_amount, "rewardBasis": c.reward_basis,
        }
    return out
