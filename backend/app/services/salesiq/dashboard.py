"""SalesIQ aggregator — role-aware dashboard payload.

Achievement is measured as SOV (£) per pillar (Connectivity/Cloud/Mobile) against the
job-title targets, plus GM and order count as secondary figures. Managers also get team
overall figures (month / quarter / year). A month can be selected for viewing.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func

from ...models import Call, User
from . import fincal, sales, trackers
from .roles import OPPS_TARGET_PER_DAY, targets_for, user_agent_match

_SUBTOTAL_FIELDS = ("gm", "mobile", "cloud", "connectivity", "other")


def _mine(user: User, o: dict) -> bool:
    return user_agent_match(user, o.get("agent"))


def _pct(actual, target):
    return round(actual / target * 100) if target else None


def _rag(pct):
    if pct is None:
        return "none"
    return "green" if pct >= 80 else "amber" if pct >= 50 else "red"


def _activity(db, user: User, cur: dict, today: date, orders_mtd: int, targets: dict) -> dict:
    start_dt = fincal.to_dt(cur["start"])
    today_dt = fincal.to_dt(today)
    week_start = fincal.to_dt(fincal.period_bounds(today, "weekly")["start"])

    def agg(since, until=None):
        q = (db.query(func.count(Call.id), func.coalesce(func.sum(Call.duration_sec), 0))
             .filter(Call.host_id == user.id, Call.started_at >= since))
        if until is not None:
            q = q.filter(Call.started_at < until)
        n, secs = q.one()
        return int(n or 0), int(secs or 0)

    dials_today, talk_today = agg(today_dt, today_dt + timedelta(days=1))
    dials_week, talk_week = agg(week_start)
    dials_mtd, talk_mtd = agg(start_dt)
    conv_mtd = (db.query(func.count(Call.id))
                .filter(Call.host_id == user.id, Call.started_at >= start_dt,
                        Call.duration_sec > 60).scalar() or 0)
    days_elapsed = max(1, (today - cur["start"]).days + 1)
    talk_target = int(targets["talkMinsPerDay"]) * 60
    dial_target = int(targets["dialsPerDay"])
    avg_dials = round(dials_mtd / days_elapsed, 1)
    avg_talk = int(talk_mtd / days_elapsed)
    return {
        "connected": True,
        "dialsToday": dials_today, "dialsWeek": dials_week, "dialsMTD": dials_mtd,
        "avgDialsPerDay": avg_dials, "dialsTarget": dial_target,
        "dialsTodayPct": _pct(dials_today, dial_target),
        "avgDialsPct": _pct(avg_dials, dial_target),
        "talkTimeTodaySec": talk_today, "talkTimeWeekSec": talk_week, "talkTimeMTDSec": talk_mtd,
        "avgTalkPerDaySec": avg_talk, "talkTargetSec": talk_target,
        "talkTodayPct": _pct(talk_today, talk_target),
        "avgTalkPct": _pct(avg_talk, talk_target),
        "dialToConvRate": round(conv_mtd / dials_mtd, 3) if dials_mtd else 0,
        "convToOrderRate": round(orders_mtd / conv_mtd, 3) if conv_mtd else 0,
        "conversationsMTD": int(conv_mtd),
    }


def _sov(orders):
    return round(sum(o["sov"] for o in orders), 2)


def _norm_lead_status(s: str) -> str:
    s = (s or "").lower()
    if "won" in s:
        return "won"
    if any(k in s for k in ("reject", "lost", "dead", "declin")):
        return "rejected"
    if any(k in s for k in ("not contact", "uncontact", "new", "unworked", "pending")):
        return "notContacted"
    return "inProgress"


def _rep_leads(user: User, cur: dict) -> dict:
    if not trackers.leads_configured():
        return {"connected": False}
    rows = [l for l in trackers.lead_rows()
            if user_agent_match(user, l.get("rep"))
            and l.get("date") and cur["start"] <= l["date"] <= cur["end"]]
    breakdown = {"won": 0, "inProgress": 0, "rejected": 0, "notContacted": 0}
    by_bc, items = {}, []
    for l in rows:
        st = _norm_lead_status(l.get("status"))
        breakdown[st] += 1
        bc = l.get("bc") or "Unknown"
        b = by_bc.setdefault(bc, {"bcName": bc, "count": 0, "won": 0, "rejected": 0})
        b["count"] += 1
        if st == "won":
            b["won"] += 1
        elif st == "rejected":
            b["rejected"] += 1
        items.append({"bc": l.get("bc"), "company": l["company"],
                      "date": l["date"].isoformat() if l.get("date") else None,
                      "status": l.get("status"), "outcome": l.get("outcome")})
    for b in by_bc.values():
        b["convRate"] = round(b["won"] / b["count"], 3) if b["count"] else None
    return {"connected": True, "totalReceived": len(rows), "statusBreakdown": breakdown,
            "byBC": sorted(by_bc.values(), key=lambda x: -x["count"]), "leads": items[:100]}


def _rep_opps(user: User, cur: dict) -> dict:
    if not trackers.activity_configured():
        return {"connected": False}
    rows = [a for a in trackers.activity_for(cur["year"], cur["month"])
            if user_agent_match(user, a.get("agent"))]
    opps = round(sum(a.get("opps") or 0 for a in rows))
    f2f = round(sum(a.get("f2f") or 0 for a in rows))
    wd = fincal.weekdays_between(cur["start"], cur["end"])
    target = OPPS_TARGET_PER_DAY * wd
    return {"connected": True, "oppsMTD": opps, "target": target, "pct": _pct(opps, target),
            "perDayTarget": OPPS_TARGET_PER_DAY, "workingDays": wd, "f2fMTD": f2f}


def _team_overall(targets: dict, anchor: date, cur: dict) -> dict:
    """Whole-team SOV/GM (manager view) for month / quarter / year vs the title target."""
    def confirmed(periods):
        return [o for (y, m) in periods for o in sales.orders_for(y, m) if o["placed"]]

    month_o = [o for o in sales.orders_for(cur["year"], cur["month"]) if o["placed"]]
    qtr_o = confirmed(fincal.quarter_months(anchor))
    yr_o = confirmed(fincal.fy_months(anchor))
    m_sov, q_sov, y_sov = _sov(month_o), _sov(qtr_o), _sov(yr_o)
    m_t, q_t, y_t = targets["monthlySov"], targets["quarterlySov"], targets["annualSov"]
    return {
        "month": {"sov": m_sov, "gm": round(sum(o["gm"] for o in month_o), 2),
                  "orders": len(month_o), "target": m_t, "pct": _pct(m_sov, m_t)},
        "quarter": {"sov": q_sov, "orders": len(qtr_o), "target": q_t, "pct": _pct(q_sov, q_t)},
        "year": {"sov": y_sov, "orders": len(yr_o), "target": y_t, "pct": _pct(y_sov, y_t)},
    }


def rep_dashboard(db, user: User, period: str = "mtd", role: str = "rep",
                  month: str | None = None) -> dict:
    today = date.today()
    if month and len(month) >= 7:
        cur = fincal.sales_month(int(month[:4]), int(month[5:7]))
        is_current = (cur["year"], cur["month"]) == \
            (fincal.current_sales_month(today)["year"], fincal.current_sales_month(today)["month"])
    else:
        cur = fincal.current_sales_month(today)
        is_current = True
    anchor = date(cur["year"], cur["month"], 15)
    targets = targets_for(db, user, role)

    month_orders = [o for o in sales.orders_for(cur["year"], cur["month"]) if _mine(user, o)]
    confirmed = [o for o in month_orders if o["placed"]]
    pending = [o for o in month_orders if not o["placed"]]
    orders_mtd = len(confirmed)
    gm_mtd = round(sum(o["gm"] for o in confirmed), 2)
    conn_mtd = round(sum(o["connectivity"] for o in confirmed), 2)
    cloud_mtd = round(sum(o["cloud"] for o in confirmed), 2)
    mobile_mtd = round(sum(o["mobile"] for o in confirmed), 2)
    sov_mtd = round(conn_mtd + cloud_mtd + mobile_mtd, 2)

    def sum_sov(periods):
        return round(sum(o["sov"] for (y, m) in periods for o in sales.orders_for(y, m)
                         if _mine(user, o) and o["placed"]), 2)

    qtd_sov = sum_sov(fincal.quarter_months(anchor))
    ytd_sov = sum_sov(fincal.fy_months(anchor))

    days_elapsed = max(1, (today - cur["start"]).days + 1)
    total_days = (cur["end"] - cur["start"]).days + 1
    run_rate = round(sov_mtd / days_elapsed * total_days) if is_current else None

    weeks: dict[str, list] = {}
    for o in month_orders:
        weeks.setdefault(o["week"] or "Week 1", []).append(o)

    def wk_key(w):
        d = "".join(c for c in w if c.isdigit())
        return int(d) if d else 99

    monthly = []
    for wk in sorted(weeks, key=wk_key):
        ws = weeks[wk]
        subtotal = {f: round(sum(x[f] for x in ws), 2) for f in _SUBTOTAL_FIELDS}
        monthly.append({"week": wk, "orders": ws, "weekSubtotal": subtotal})

    sov_target = targets["monthlySov"]
    pct = _pct(sov_mtd, sov_target)

    sm = sales.status()
    avail = [{"year": m["period"][0], "month": m["period"][1],
              "value": f"{m['period'][0]:04d}-{m['period'][1]:02d}",
              "label": fincal.sales_month(m["period"][0], m["period"][1])["label"]}
             for m in sm.get("months", [])]
    avail.sort(key=lambda x: x["value"], reverse=True)

    payload = {
        "meta": {
            "userId": user.id, "name": user.name, "role": role, "viewType": "rep",
            "period": period,
            "periodLabel": f"{cur['label']} (MTD)" if is_current else cur["label"],
            "financialQuarter": fincal.financial_quarter(anchor)["label"],
            "salesMonthStart": cur["start"].isoformat(),
            "salesMonthLabel": cur["label"],
            "selectedMonth": f"{cur['year']:04d}-{cur['month']:02d}",
            "isCurrentMonth": is_current,
            "availableMonths": avail,
            "computedAt": datetime.utcnow().isoformat() + "Z",
            "salesConfigured": sales.configured(),
        },
        "performance": {
            "sovMTD": sov_mtd, "sovTarget": sov_target, "sovPct": pct, "rag": _rag(pct),
            "connectivity": {"mtd": conn_mtd, "target": targets["connectivity"]},
            "cloud": {"mtd": cloud_mtd, "target": targets["cloud"]},
            "mobile": {"mtd": mobile_mtd, "target": targets["mobile"]},
            "gmMTD": gm_mtd, "ordersMTD": orders_mtd,
            "runRate": run_rate, "daysRemaining": fincal.days_remaining(today) if is_current else 0,
            "qtd": {"sov": qtd_sov, "target": targets["quarterlySov"], "pct": _pct(qtd_sov, targets["quarterlySov"])},
            "ytd": {"sov": ytd_sov, "target": targets["annualSov"], "pct": _pct(ytd_sov, targets["annualSov"])},
            "pendingCount": len(pending),
            "pendingValueSov": round(sum(o["sov"] for o in pending), 2),
        },
        "monthlyOrders": monthly,
        "pendingOrders": [{**o, "daysPending": None, "atRisk": False} for o in pending],
        "activity": _activity(db, user, cur, today, orders_mtd, targets),
        "opps": _rep_opps(user, cur),
        "leads": _rep_leads(user, cur),
    }
    if role == "manager":
        payload["overall"] = _team_overall(targets, anchor, cur)
    return payload


# ============================================================ Business Creator view
def _recent_months(cur: dict, n: int = 6):
    out, y, m = [], cur["year"], cur["month"]
    for _ in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


def _bc_leads_in(user: User, win: dict) -> list[dict]:
    return [l for l in trackers.lead_rows()
            if user_agent_match(user, l.get("bc")) and l.get("date")
            and win["start"] <= l["date"] <= win["end"]]


def bc_dashboard(db, user: User, period: str = "mtd", month: str | None = None) -> dict:
    """A Business Creator's own view: leads generated vs target, F2F, conversion, where their
    leads go (by receiving rep), recent leads, and their logged activity."""
    today = date.today()
    if month and len(month) >= 7:
        cur = fincal.sales_month(int(month[:4]), int(month[5:7]))
        ccur = fincal.current_sales_month(today)
        is_current = (cur["year"], cur["month"]) == (ccur["year"], ccur["month"])
    else:
        cur = fincal.current_sales_month(today)
        is_current = True
    anchor = date(cur["year"], cur["month"], 15)

    tgt = targets_for(db, user, "bc")
    lead_target = int(tgt.get("leads") or 40)
    f2f_target = max(1, round(lead_target / 5))

    leads = _bc_leads_in(user, cur) if trackers.leads_configured() else []
    n = len(leads)
    f2f = sum(1 for l in leads if l.get("f2f"))
    won = sum(1 for l in leads if l.get("signed"))
    rejected = sum(1 for l in leads if l.get("rejected"))
    lead_pct = _pct(n, lead_target)

    by_rec: dict[str, dict] = {}
    for l in leads:
        rec = l.get("rep") or "Unassigned"
        e = by_rec.setdefault(rec, {"rep": rec, "count": 0, "won": 0})
        e["count"] += 1
        if l.get("signed"):
            e["won"] += 1
    for e in by_rec.values():
        e["convRate"] = round(e["won"] / e["count"], 3) if e["count"] else None
    by_receiver = sorted(by_rec.values(), key=lambda x: -x["count"])

    items = [{"company": l["company"], "rep": l.get("rep"),
              "date": l["date"].isoformat() if l.get("date") else None,
              "leadType": l.get("leadType"), "status": l.get("status"),
              "f2f": l.get("f2f"), "signed": l.get("signed")}
             for l in sorted(leads, key=lambda x: x["date"] or date.min, reverse=True)[:60]]

    trend = []
    for (yy, mm) in _recent_months(cur, 6):
        w = fincal.sales_month(yy, mm)
        ls = _bc_leads_in(user, w) if trackers.leads_configured() else []
        trend.append({"label": f"{fincal.MONTH_ABBR[mm]}", "leads": len(ls),
                      "won": sum(1 for l in ls if l.get("signed"))})

    # GM generated this month + the BC's own Monthly Orders come straight from the BC's OWN tab in
    # the Sales Tracker — exactly like a rep. The tracker already splits GM per agent, so each row
    # on the BC's tab carries THEIR share of the GM at THEIR agreed Split % (e.g. 20/40/60%). So
    # gmGenerated is just the sum of the BC's placed orders, and Split With / Split % are shown as
    # recorded (the closing rep + the BC's own share) with no re-derivation.
    bc_orders = [o for o in sales.orders_for(cur["year"], cur["month"]) if _mine(user, o)]
    gm_generated = round(sum(o["gm"] for o in bc_orders if o.get("placed")), 2)

    bweeks: dict[str, list] = {}
    for o in bc_orders:
        bweeks.setdefault(o.get("week") or "Week 1", []).append(o)

    def _bwk_key(w):
        d = "".join(c for c in w if c.isdigit())
        return int(d) if d else 99

    bc_monthly = [{"week": wk, "orders": bweeks[wk],
                   "weekSubtotal": {f: round(sum(x.get(f, 0) or 0 for x in bweeks[wk]), 2)
                                    for f in _SUBTOTAL_FIELDS}}
                  for wk in sorted(bweeks, key=_bwk_key)]

    # Dials & talk time are TODAY's, from CallIQ; leads-logged stays MTD from the tracker.
    today_dt = datetime(today.year, today.month, today.day)
    dn, dsec = (db.query(func.count(Call.id), func.coalesce(func.sum(Call.duration_sec), 0))
                .filter(Call.host_id == user.id, Call.started_at >= today_dt).one())
    leads_logged = 0
    if trackers.activity_configured():
        arows = [a for a in trackers.activity_for(cur["year"], cur["month"])
                 if user_agent_match(user, a.get("agent"))]
        leads_logged = round(sum(a.get("leads") or 0 for a in arows))
    activity = {"connected": True, "dialsToday": int(dn or 0),
                "talkSecToday": int(dsec or 0), "leadsLogged": leads_logged}

    sm = sales.status()
    avail = [{"value": f"{m['period'][0]:04d}-{m['period'][1]:02d}",
              "label": fincal.sales_month(m["period"][0], m["period"][1])["label"]}
             for m in sm.get("months", [])]
    avail.sort(key=lambda x: x["value"], reverse=True)

    return {
        "meta": {"userId": user.id, "name": user.name, "role": "bc", "viewType": "bc",
                 "periodLabel": f"{cur['label']} (MTD)" if is_current else cur["label"],
                 "financialQuarter": fincal.financial_quarter(anchor)["label"],
                 "salesMonthLabel": cur["label"],
                 "selectedMonth": f"{cur['year']:04d}-{cur['month']:02d}",
                 "isCurrentMonth": is_current, "availableMonths": avail,
                 "computedAt": datetime.utcnow().isoformat() + "Z",
                 "leadsConfigured": trackers.leads_configured(),
                 "activityConfigured": trackers.activity_configured()},
        "performance": {
            "leadsMTD": n, "leadTarget": lead_target, "leadPct": lead_pct, "rag": _rag(lead_pct),
            "gmGenerated": gm_generated,
            "f2f": f2f, "f2fTarget": f2f_target, "f2fPct": _pct(f2f, f2f_target),
            "won": won, "wonPct": _pct(won, n), "rejected": rejected,
        },
        "byReceiver": by_receiver,
        "trend": trend,
        "leads": items,
        "monthlyOrders": bc_monthly,
        "activity": activity,
    }
