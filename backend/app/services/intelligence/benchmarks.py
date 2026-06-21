"""Performance benchmarks (Roadmap Phase 0 — the benchmark engine).

Turns the per-call metrics we already capture into *comparative* intelligence: each rep's call
quality and orders over time, their line against the **team average**, and where they **rank** among
their peers. This is the foundation for the motivational trend charts and, later, the insight engine
and league tables. Pure aggregation over existing data — no new dependencies.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy.orm import joinedload

from ...models import Call, Team, User
from .common import _avg_scores, _mean, quality_100
from ..salesiq.roles import salesiq_role


def _rep_group(db, u: User) -> tuple[str | None, str | None, str | None]:
    """(team_name, group_slug, sales_role). group_slug ∈ business_creators|value|volume|other.
    sales_role is None for Operations / non-sales (excluded from the league)."""
    team_name = None
    if u and u.team_id:
        t = db.get(Team, u.team_id)
        team_name = t.name if t else None
    role = salesiq_role(u.role, u.job_title, team_name) if u else None
    tm = (team_name or "").lower()
    if role == "bc" or "creator" in tm:
        group = "business_creators"
    elif "value" in tm:
        group = "value"
    elif "volume" in tm:
        group = "volume"
    else:
        group = "other"
    return team_name, group, role


def _team_call_rows(db, start: datetime, asof: datetime) -> list[dict]:
    """Lightweight per-call rows for the whole team in [start, asof): host, date, quality, order."""
    calls = (db.query(Call).options(joinedload(Call.analysis))
             .filter(Call.started_at >= start, Call.started_at < asof,
                     Call.status == "completed").all())
    qmap = _avg_scores(db, [c.id for c in calls])
    return [{
        "host_id": c.host_id,
        "date": c.started_at.date(),
        "quality": quality_100(qmap[c.id]) if c.id in qmap else None,
        "is_order": c.outcome == "order_placed",
    } for c in calls]


def _weekly(rows: list[dict], weeks: int, asof: date, rep_count: int = 1) -> list[dict]:
    """Bin rows into weekly points: mean quality, total orders, and orders-per-rep (for the team line)."""
    buckets: dict[int, list[dict]] = {}
    for r in rows:
        wk = (asof - r["date"]).days // 7
        if 0 <= wk < weeks:
            buckets.setdefault(wk, []).append(r)
    series = []
    for wk in range(weeks - 1, -1, -1):                  # oldest → newest
        wr = buckets.get(wk, [])
        wk_start = asof - timedelta(days=(wk + 1) * 7 - 1)
        orders = sum(1 for r in wr if r["is_order"])
        series.append({
            "label": wk_start.strftime("%d %b"),
            "quality": _mean([r["quality"] for r in wr]),
            "orders": orders,
            "ordersPerRep": round(orders / rep_count, 1) if rep_count else orders,
            "calls": len(wr),
        })
    return series


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def rep_vs_team(db, user_id: int, weeks: int = 12, asof: datetime | None = None) -> dict:
    """Rep's weekly quality + orders against the team average, plus their rank among peers."""
    asof = asof or datetime.utcnow()
    start = asof - timedelta(days=weeks * 7)
    aday = asof.date()
    team_rows = _team_call_rows(db, start, asof)

    # who counts as a "rep" this window = anyone who logged a completed call
    host_ids = {r["host_id"] for r in team_rows if r["host_id"]}
    rep_count = max(1, len(host_ids))

    rep_rows = [r for r in team_rows if r["host_id"] == user_id]
    rep_series = _weekly(rep_rows, weeks, aday)
    team_series = _weekly(team_rows, weeks, aday, rep_count=rep_count)

    # per-rep aggregates over the whole window → rank
    agg: dict[int, dict] = {}
    for r in team_rows:
        if not r["host_id"]:
            continue
        a = agg.setdefault(r["host_id"], {"q": [], "orders": 0})
        if r["quality"] is not None:
            a["q"].append(r["quality"])
        if r["is_order"]:
            a["orders"] += 1
    quality_by_rep = {h: (_mean(a["q"]) if a["q"] else None) for h, a in agg.items()}
    orders_by_rep = {h: a["orders"] for h, a in agg.items()}

    def _rank(value_map, higher_better=True):
        vals = [v for v in value_map.values() if v is not None]
        me = value_map.get(user_id)
        if me is None or not vals:
            return None
        better = sum(1 for v in vals if (v > me if higher_better else v < me))
        rank = better + 1
        pct = round(100 * (len(vals) - rank) / max(1, len(vals) - 1)) if len(vals) > 1 else 100
        return {"rank": rank, "of": len(vals), "label": f"{_ordinal(rank)} of {len(vals)}", "percentile": pct}

    return {
        "weeks": weeks,
        "repName": (db.get(User, user_id).name if db.get(User, user_id) else None),
        "repSeries": rep_series,
        "teamSeries": team_series,
        "myQuality": quality_by_rep.get(user_id),
        "teamQuality": _mean([v for v in quality_by_rep.values() if v is not None]),
        "myOrders": orders_by_rep.get(user_id, 0),
        "teamOrdersAvg": round(sum(orders_by_rep.values()) / rep_count, 1) if rep_count else 0,
        "qualityRank": _rank(quality_by_rep, higher_better=True),
        "ordersRank": _rank(orders_by_rep, higher_better=True),
    }


def league(db, days: int = 30, asof: datetime | None = None) -> dict:
    """Team league table — every rep ranked by call quality, with orders and 'most improved'
    (quality change vs the prior equal window). For the Command Centre."""
    asof = asof or datetime.utcnow()
    start = asof - timedelta(days=days)
    prior_start = start - timedelta(days=days)
    cur = _team_call_rows(db, start, asof)
    prior = _team_call_rows(db, prior_start, start)

    def _agg(rs):
        m: dict[int, dict] = {}
        for r in rs:
            if not r["host_id"]:
                continue
            a = m.setdefault(r["host_id"], {"q": [], "orders": 0, "calls": 0})
            a["calls"] += 1
            if r["quality"] is not None:
                a["q"].append(r["quality"])
            if r["is_order"]:
                a["orders"] += 1
        return m

    cagg, pagg = _agg(cur), _agg(prior)
    rows = []
    for hid, a in cagg.items():
        u = db.get(User, hid)
        team_name, group, role = _rep_group(db, u)
        if role is None:           # Operations / non-sales — they don't make sales calls
            continue
        q = _mean(a["q"])
        pq = _mean(pagg.get(hid, {}).get("q", [])) if hid in pagg else None
        rows.append({
            "userId": hid,
            "name": ((u.short_name or u.name) if u else None),
            "team": team_name, "group": group,
            "quality": q, "orders": a["orders"], "calls": a["calls"],
            "deltaQuality": (round(q - pq, 1) if (q is not None and pq is not None) else None),
        })
    rows.sort(key=lambda r: (r["quality"] is None, -(r["quality"] or 0)))
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    improved = [r for r in rows if r["deltaQuality"] and r["deltaQuality"] > 0]
    most = max(improved, key=lambda r: r["deltaQuality"]) if improved else None
    return {
        "days": days,
        "teamQuality": _mean([r["quality"] for r in rows if r["quality"] is not None]),
        "reps": rows,
        "mostImproved": ({"userId": most["userId"], "name": most["name"], "delta": most["deltaQuality"]} if most else None),
    }
