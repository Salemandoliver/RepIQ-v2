"""Weekly Forecast services — the data foundation (Phase 1).

Responsibilities:
- Week helpers (BT financial week ↔ Sales Tracker "Week N" label within the sales month).
- Forecast CRUD with the lock rules: a rep submits once, then it's locked to them; only a manager
  can edit/unlock.
- Achievement: placed-order SOV matched to the rep for the week (Data = connectivity, Cloud, Mobile),
  reusing the exact attribution the rep dashboard uses (``user_agent_match`` + ``placed``).
- Leave-aware helpers (who's on leave, whole-week "excused").
- Week-close snapshot → ``WeeklyForecastResult`` history.
- Forecast Reliability Score (pure, DB-free maths so it's unit-testable): hit-rate (≥100% = hit),
  accuracy (penalises BOTH over- and under-forecasting), trend, and submission discipline.

Nothing here is user-facing yet; routers/UI come in later phases.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from ...models import User
from ..hr import leave as hr_leave
from ...services.salesiq import fincal, sales
from ...services.salesiq.roles import role_for_user, user_agent_match
from .models import WeeklyForecast, WeeklyForecastResult

# --- scoring constants (tunable) ------------------------------------------------------------------
HIT_THRESHOLD_PCT = 100.0          # a week "hits" only at ≥100% of forecast (Salem's decision)
RELIABILITY_WINDOW = 8             # rolling weeks the reliability score is built from
ON_TIME_HOUR = 11                  # forecast is "on time" if submitted by Monday 11:00
W_HIT, W_ACC, W_TREND, W_DISC = 0.40, 0.30, 0.15, 0.15   # reliability component weights


# ================================================================== week helpers
def current_week(d: date | None = None) -> dict:
    """The BT financial week (Mon–Sun) containing ``d`` (default today)."""
    return fincal.financial_week(d or date.today())


def week_bounds(week_year: int, week_number: int) -> dict:
    return fincal.financial_week_by_number(week_number, week_year)


def tracker_week_label(d: date) -> str:
    """The Sales Tracker labels orders 'Week 1..N' *within a sales-month tab*. Map a date to that
    label: the index of its Monday within the sales month it belongs to.

    NOTE: this alignment is verified against the real sheet in Phase 1 before anything relies on it.
    """
    sm = fincal.current_sales_month(d)
    monday = d - timedelta(days=d.weekday())
    idx = (monday - sm["start"]).days // 7 + 1
    return f"Week {max(1, idx)}"


# ================================================================== rep eligibility
def is_rep(db: Session, user: User) -> bool:
    """Only Sales Reps forecast — BCs, managers, admins and Operations do not."""
    return role_for_user(db, user) == "rep"


def eligible_reps(db: Session, team: str | None = None) -> list[User]:
    out = []
    for u in db.query(User).filter(User.active.is_(True)).order_by(User.name).all():
        if role_for_user(db, u) != "rep":
            continue
        if team and team.lower() not in ("all", ""):
            tname = (u.team.name if u.team else "") or ""
            if team.lower() not in tname.lower():
                continue
        out.append(u)
    return out


# ================================================================== forecast CRUD
def get_forecast(db: Session, user_id: int, week_year: int, week_number: int) -> WeeklyForecast | None:
    return (db.query(WeeklyForecast)
            .filter(WeeklyForecast.user_id == user_id,
                    WeeklyForecast.week_year == week_year,
                    WeeklyForecast.week_number == week_number).first())


def forecast_to_dict(fc: WeeklyForecast | None) -> dict | None:
    if not fc:
        return None
    return {
        "userId": fc.user_id, "weekYear": fc.week_year, "weekNumber": fc.week_number,
        "data": round(fc.data_sov or 0.0, 2), "cloud": round(fc.cloud_sov or 0.0, 2),
        "mobile": round(fc.mobile_sov or 0.0, 2), "total": fc.total_sov,
        "submitted": fc.submitted_at is not None,
        "submittedAt": fc.submitted_at.isoformat() + "Z" if fc.submitted_at else None,
        "onTime": bool(fc.on_time), "locked": bool(fc.locked),
        "editedBy": fc.edited_by_id, "editNote": fc.edit_note,
    }


def _on_time(week_start: date, when: datetime) -> bool:
    return when <= datetime.combine(week_start, time(ON_TIME_HOUR, 0))


def submit_forecast(db: Session, user: User, week_year: int, week_number: int,
                    data: float, cloud: float, mobile: float, when: datetime | None = None) -> WeeklyForecast:
    """Rep path. Creates the forecast and locks it. Raises if already locked (rep can't re-edit)."""
    when = when or datetime.utcnow()
    fc = get_forecast(db, user.id, week_year, week_number)
    if fc and fc.locked:
        raise PermissionError("This week's forecast is locked. Ask your manager to change it.")
    if not fc:
        fc = WeeklyForecast(user_id=user.id, week_year=week_year, week_number=week_number)
        db.add(fc)
    fc.data_sov = round(float(data or 0.0), 2)
    fc.cloud_sov = round(float(cloud or 0.0), 2)
    fc.mobile_sov = round(float(mobile or 0.0), 2)
    fc.submitted_at = when
    fc.submitted_by_id = user.id
    fc.on_time = _on_time(week_bounds(week_year, week_number)["start"], when)
    fc.locked = True
    db.commit()
    return fc


def manager_set_forecast(db: Session, manager: User, user_id: int, week_year: int, week_number: int,
                         data: float | None = None, cloud: float | None = None, mobile: float | None = None,
                         unlock: bool = False, note: str | None = None) -> WeeklyForecast:
    """Manager path. May edit any forecast and optionally unlock it so the rep can re-enter."""
    fc = get_forecast(db, user_id, week_year, week_number)
    if not fc:
        fc = WeeklyForecast(user_id=user_id, week_year=week_year, week_number=week_number,
                            submitted_at=datetime.utcnow(), submitted_by_id=user_id, on_time=False)
        db.add(fc)
    if data is not None:
        fc.data_sov = round(float(data), 2)
    if cloud is not None:
        fc.cloud_sov = round(float(cloud), 2)
    if mobile is not None:
        fc.mobile_sov = round(float(mobile), 2)
    fc.locked = not unlock
    fc.edited_by_id = manager.id
    fc.edited_at = datetime.utcnow()
    if note:
        fc.edit_note = note[:300]
    db.commit()
    return fc


# ================================================================== leave awareness
def leave_user_ids(db: Session, asof: date) -> set[int]:
    """User ids on booked leave on ``asof`` — in-app HR leave plus the SharePoint Holiday Tracker
    fallback (matched by name), mirroring the leave-aware Smart Alerts."""
    ids: set[int] = set()
    try:
        ids = {r["user_id"] for r in hr_leave.leave_rows(db, asof, asof)}
    except Exception:
        pass
    try:
        from ...services.salesiq import trackers
        from ...services.salesiq.roles import user_agent_match as _uam
        if trackers.holiday_configured():
            off = [h.get("name") for h in trackers.holiday_rows()
                   if h.get("date") == asof and str(h.get("code") or "").upper() != "B"]
            if off:
                for u in db.query(User).filter(User.active.is_(True)).all():
                    if u.id not in ids and any(_uam(u, nm) for nm in off):
                        ids.add(u.id)
    except Exception:
        pass
    return ids


def excused_week(db: Session, user: User, start: date, end: date) -> bool:
    """True if the rep is on leave for *every* working day (Mon–Fri) of the week — that week is
    excused and won't count toward their reliability score."""
    weekdays = [start + timedelta(days=i) for i in range((end - start).days + 1)
                if (start + timedelta(days=i)).weekday() < 5]
    if not weekdays:
        return False
    leave_dates: set[date] = set()
    try:
        leave_dates = {r["date"] for r in hr_leave.user_leave(db, user.id, start, end)}
    except Exception:
        pass
    if all(d in leave_dates for d in weekdays):
        return True
    # Holiday Tracker fallback
    try:
        from ...services.salesiq import trackers
        if trackers.holiday_configured():
            off = {h.get("date") for h in trackers.holiday_rows()
                   if user_agent_match(user, h.get("name")) and str(h.get("code") or "").upper() != "B"}
            return all((d in leave_dates or d in off) for d in weekdays)
    except Exception:
        pass
    return False


# ================================================================== achievement
def _mine(user: User, o: dict) -> bool:
    return user_agent_match(user, o.get("agent"))


def _working_days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)
            if (start + timedelta(days=i)).weekday() < 5]


def compute_achievement(db: Session, user: User, week_year: int, week_number: int,
                        asof: date | None = None) -> dict:
    """A rep's placed-order SOV for the week, split Data/Cloud/Mobile, vs their forecast.

    Reuses the rep-dashboard attribution: an order is the rep's if ``user_agent_match`` on the
    tracker ``agent`` field (the tracker already holds each agent's own share), it's ``placed``, and
    it falls in this week's tracker label.
    """
    asof = asof or date.today()
    bounds = week_bounds(week_year, week_number)
    wk_start, wk_end = bounds["start"], bounds["end"]
    sm = fincal.current_sales_month(wk_start)
    label = tracker_week_label(wk_start)

    orders = [o for o in sales.orders_for(sm["year"], sm["month"])
              if _mine(user, o) and o.get("placed") and (o.get("week") or "Week 1") == label]
    actual_data = round(sum(o["connectivity"] for o in orders), 2)
    actual_cloud = round(sum(o["cloud"] for o in orders), 2)
    actual_mobile = round(sum(o["mobile"] for o in orders), 2)
    actual_total = round(actual_data + actual_cloud + actual_mobile, 2)

    fc = get_forecast(db, user.id, week_year, week_number)
    f_data = round(fc.data_sov, 2) if fc else 0.0
    f_cloud = round(fc.cloud_sov, 2) if fc else 0.0
    f_mobile = round(fc.mobile_sov, 2) if fc else 0.0
    f_total = round(f_data + f_cloud + f_mobile, 2)

    def pct(actual: float, forecast: float) -> float | None:
        if forecast and forecast > 0:
            return round(actual / forecast * 100, 1)
        return None

    overall_pct = pct(actual_total, f_total)
    hit = bool(f_total > 0 and actual_total >= f_total)

    # Pacing — only meaningful while the week is in progress.
    pacing = None
    if wk_start <= asof <= wk_end:
        total_wd = len(_working_days(wk_start, wk_end)) or 1
        elapsed_wd = len(_working_days(wk_start, min(asof, wk_end)))
        expected = round(elapsed_wd / total_wd * 100)
        pacing = {"workingDaysElapsed": elapsed_wd, "workingDaysTotal": total_wd,
                  "expectedPct": expected,
                  "onTrack": (overall_pct is not None and overall_pct >= expected)}

    return {
        "week": {"year": week_year, "number": week_number, "label": bounds["label"],
                 "trackerLabel": label, "start": wk_start.isoformat(), "end": wk_end.isoformat()},
        "forecast": {"data": f_data, "cloud": f_cloud, "mobile": f_mobile, "total": f_total},
        "actual": {"data": actual_data, "cloud": actual_cloud, "mobile": actual_mobile, "total": actual_total},
        "pct": {"data": pct(actual_data, f_data), "cloud": pct(actual_cloud, f_cloud),
                "mobile": pct(actual_mobile, f_mobile), "overall": overall_pct},
        "hit": hit,
        "submitted": bool(fc and fc.submitted_at),
        "locked": bool(fc and fc.locked),
        "orders": len(orders),
        "pacing": pacing,
        "salesConfigured": sales.configured(),
    }


def team_forecast(db: Session, week_year: int, week_number: int, team: str | None = None) -> dict:
    """Team totals (Data/Cloud/Mobile forecast, actual, %) plus a per-rep row for each rep."""
    reps = eligible_reps(db, team)
    rows, tot = [], {"fData": 0.0, "fCloud": 0.0, "fMobile": 0.0,
                     "aData": 0.0, "aCloud": 0.0, "aMobile": 0.0}
    for u in reps:
        ach = compute_achievement(db, u, week_year, week_number)
        f, a = ach["forecast"], ach["actual"]
        tot["fData"] += f["data"]; tot["fCloud"] += f["cloud"]; tot["fMobile"] += f["mobile"]
        tot["aData"] += a["data"]; tot["aCloud"] += a["cloud"]; tot["aMobile"] += a["mobile"]
        rel = reliability(db, u)
        rows.append({"userId": u.id, "name": u.short_name or u.name,
                     "avatarColor": getattr(u, "avatar_color", None),
                     "forecast": f, "actual": a, "pct": ach["pct"], "hit": ach["hit"],
                     "submitted": ach["submitted"], "pacing": ach["pacing"],
                     "reliabilityScore": rel.get("score"), "reliabilityBand": rel.get("band"),
                     "reliabilityWeeks": rel.get("weeks")})

    def _p(a: float, f: float):
        return round(a / f * 100, 1) if f > 0 else None

    f_total = round(tot["fData"] + tot["fCloud"] + tot["fMobile"], 2)
    a_total = round(tot["aData"] + tot["aCloud"] + tot["aMobile"], 2)
    bounds = week_bounds(week_year, week_number)
    return {
        "week": {"year": week_year, "number": week_number, "label": bounds["label"],
                 "start": bounds["start"].isoformat(), "end": bounds["end"].isoformat()},
        "totals": {
            "forecast": {"data": round(tot["fData"], 2), "cloud": round(tot["fCloud"], 2),
                         "mobile": round(tot["fMobile"], 2), "total": f_total},
            "actual": {"data": round(tot["aData"], 2), "cloud": round(tot["aCloud"], 2),
                       "mobile": round(tot["aMobile"], 2), "total": a_total},
            "pct": {"data": _p(tot["aData"], tot["fData"]), "cloud": _p(tot["aCloud"], tot["fCloud"]),
                    "mobile": _p(tot["aMobile"], tot["fMobile"]), "overall": _p(a_total, f_total)},
        },
        "reps": rows,
        "repCount": len(reps),
        "salesConfigured": sales.configured(),
    }


def missing_forecasts(db: Session, week_year: int, week_number: int, asof: date | None = None) -> list[dict]:
    """Reps who haven't submitted this week's forecast — excluding anyone on leave today."""
    asof = asof or date.today()
    on_leave = leave_user_ids(db, asof)
    out = []
    for u in eligible_reps(db):
        if u.id in on_leave:
            continue
        fc = get_forecast(db, u.id, week_year, week_number)
        if not (fc and fc.submitted_at):
            out.append({"userId": u.id, "name": u.short_name or u.name})
    return out


# ================================================================== week close + history
def _upsert_result(db: Session, user_id: int, week_year: int, week_number: int, **vals) -> WeeklyForecastResult:
    row = (db.query(WeeklyForecastResult)
           .filter(WeeklyForecastResult.user_id == user_id,
                   WeeklyForecastResult.week_year == week_year,
                   WeeklyForecastResult.week_number == week_number).first())
    if not row:
        row = WeeklyForecastResult(user_id=user_id, week_year=week_year, week_number=week_number)
        db.add(row)
    for k, v in vals.items():
        setattr(row, k, v)
    return row


def close_week(db: Session, week_year: int, week_number: int) -> list[WeeklyForecastResult]:
    """Snapshot each rep's forecast vs actuals for a finished week into immutable history. Idempotent
    (re-running overwrites the same row), so it's safe for the Monday worker to call."""
    bounds = week_bounds(week_year, week_number)
    out = []
    for u in eligible_reps(db):
        ach = compute_achievement(db, u, week_year, week_number, asof=bounds["end"])
        fc = get_forecast(db, u.id, week_year, week_number)
        f, a = ach["forecast"], ach["actual"]
        excused = excused_week(db, u, bounds["start"], bounds["end"])
        row = _upsert_result(
            db, u.id, week_year, week_number,
            forecast_data=f["data"], forecast_cloud=f["cloud"], forecast_mobile=f["mobile"],
            actual_data=a["data"], actual_cloud=a["cloud"], actual_mobile=a["mobile"],
            achievement_pct=(ach["pct"]["overall"] or 0.0),
            hit=ach["hit"], submitted=ach["submitted"],
            on_time=bool(fc.on_time) if fc else False, excused=excused)
        out.append(row)
    db.commit()
    return out


# ================================================================== reliability (pure maths)
def _band(score: float | None) -> str:
    if score is None:
        return "none"
    if score >= 70:
        return "green"
    if score >= 45:
        return "amber"
    return "red"


def _trend(achievements: list[float]) -> float:
    """0..1 trend from a newest-first list of achievement %. 0.5 = flat; >0.5 improving."""
    if len(achievements) < 2:
        return 0.5
    capped = [min(max(a, 0.0), 150.0) for a in achievements]   # newest-first
    half = len(capped) // 2 or 1
    recent = capped[:half]
    older = capped[half:] or capped[-1:]
    rm, om = sum(recent) / len(recent), sum(older) / len(older)
    return max(0.0, min(1.0, 0.5 + (rm - om) / 100.0))


def reliability_from_records(records: list[dict]) -> dict:
    """Pure, DB-free reliability scoring (unit-testable).

    ``records`` = newest-first list of dicts: forecast_total, actual_total, achievement_pct, hit,
    submitted, on_time, excused. Excused weeks (whole-week leave) are dropped before scoring.
    """
    scored = [r for r in records if not r.get("excused")]
    n = len(scored)
    if n == 0:
        return {"score": None, "band": "none", "weeks": 0, "hitCount": 0, "components": None}

    hit_count = sum(1 for r in scored if r.get("hit"))
    hit_rate = hit_count / n

    accs = []
    for r in scored:
        f = float(r.get("forecast_total") or 0.0)
        a = float(r.get("actual_total") or 0.0)
        if f <= 0:
            accs.append(0.0)                      # no forecast set → no accuracy credit
        else:
            err = abs(a - f) / f                  # penalises over- AND under-forecasting
            accs.append(max(0.0, 1.0 - min(err, 1.0)))
    accuracy = sum(accs) / n

    disc = sum(1 for r in scored if r.get("submitted") and r.get("on_time")) / n
    trend = _trend([float(r.get("achievement_pct") or 0.0) for r in scored])

    score = round(100 * (W_HIT * hit_rate + W_ACC * accuracy + W_TREND * trend + W_DISC * disc))
    return {
        "score": score, "band": _band(score), "weeks": n, "hitCount": hit_count,
        "components": {
            "hitRate": round(hit_rate * 100), "accuracy": round(accuracy * 100),
            "trend": round(trend * 100), "discipline": round(disc * 100),
        },
    }


def reliability(db: Session, user: User, window: int = RELIABILITY_WINDOW) -> dict:
    """Reliability score for a rep from their most recent ``window`` snapshotted weeks."""
    rows = (db.query(WeeklyForecastResult)
            .filter(WeeklyForecastResult.user_id == user.id)
            .order_by(WeeklyForecastResult.week_year.desc(), WeeklyForecastResult.week_number.desc())
            .limit(window).all())
    records = [{
        "forecast_total": (r.forecast_data + r.forecast_cloud + r.forecast_mobile),
        "actual_total": (r.actual_data + r.actual_cloud + r.actual_mobile),
        "achievement_pct": r.achievement_pct, "hit": r.hit,
        "submitted": r.submitted, "on_time": r.on_time, "excused": r.excused,
    } for r in rows]
    out = reliability_from_records(records)
    out["history"] = [{
        "weekYear": r.week_year, "weekNumber": r.week_number,
        "achievementPct": r.achievement_pct, "hit": r.hit, "excused": r.excused,
    } for r in rows]
    return out


# ================================================================== forecast signal (for everything)
def _signal_summary(name, submitted, pct, behind, score, weeks, hits, chronic, strong, sandbag):
    """One short human sentence summarising a rep's forecast standing — reused by briefs, the AI
    videos and Ask/Oracle so the language is consistent everywhere."""
    if not submitted:
        return f"{name} hasn't submitted a forecast this week."
    bits = []
    if pct is not None:
        bits.append(f"at {round(pct)}% of this week's forecast" + (" (behind pace)" if behind else ""))
    if weeks:
        bits.append(f"reliability {score}/100, hit {hits} of the last {weeks} week(s)")
    if chronic:
        bits.append("consistently missing forecast")
    elif strong:
        bits.append("a consistently reliable forecaster")
    if sandbag:
        bits.append("tends to under-forecast then beat it (sandbagging)")
    return f"{name}: " + ("; ".join(bits) if bits else "forecast on track") + "."


def rep_signal(db: Session, user: User, asof: date | None = None) -> dict:
    """Compact forecast signal for a rep — the single source the insight detectors, Smart Alerts,
    1-to-1 briefs, AI videos and Ask/Oracle all read, so the forecast factors into every analysis."""
    asof = asof or date.today()
    wk = current_week(asof)
    wy, wn = wk["week_year"], wk["number"]
    ach = compute_achievement(db, user, wy, wn, asof=asof)
    rel = reliability(db, user)
    fc = get_forecast(db, user.id, wy, wn)
    submitted = bool(fc and fc.submitted_at)
    overall = ach["pct"]["overall"]
    pacing = ach["pacing"] or {}
    behind = bool(submitted and pacing and not pacing.get("onTrack"))
    comps = rel.get("components") or {}
    weeks = rel.get("weeks") or 0
    hits = rel.get("hitCount") or 0
    score = rel.get("score")
    chronic_miss = bool(weeks >= 3 and hits / weeks <= 0.34)
    strong = bool(weeks >= 4 and score is not None and score >= 75 and hits / weeks >= 0.6)
    sandbagger = bool(weeks >= 3 and comps.get("hitRate", 0) >= 80 and comps.get("accuracy", 100) <= 45)
    return {
        "userId": user.id, "name": user.short_name or user.name,
        "week": wk["label"], "submitted": submitted, "notSubmitted": not submitted,
        "thisWeekPct": overall, "behindPace": behind, "expectedPct": pacing.get("expectedPct"),
        "forecastTotal": ach["forecast"]["total"], "actualTotal": ach["actual"]["total"],
        "reliabilityScore": score, "reliabilityBand": rel.get("band"),
        "weeks": weeks, "hitCount": hits, "components": comps,
        "chronicMiss": chronic_miss, "strong": strong, "sandbagger": sandbagger,
        "summary": _signal_summary(user.short_name or user.name, submitted, overall, behind,
                                   score, weeks, hits, chronic_miss, strong, sandbagger),
    }


def team_summary(db: Session, team: str | None = None, asof: date | None = None) -> dict:
    """Team-wide forecast signal: totals, who's missing/behind, and a per-rep signal list."""
    asof = asof or date.today()
    reps = eligible_reps(db, team)
    sigs = [rep_signal(db, u, asof) for u in reps]
    submitted = [s for s in sigs if s["submitted"]]
    f_total = round(sum(s["forecastTotal"] for s in submitted), 2)
    a_total = round(sum(s["actualTotal"] for s in submitted), 2)
    return {
        "week": current_week(asof)["label"],
        "forecastTotal": f_total, "actualTotal": a_total,
        "pct": round(a_total / f_total * 100, 1) if f_total > 0 else None,
        "missing": [s["name"] for s in sigs if not s["submitted"]],
        "behind": [s["name"] for s in sigs if s["behindPace"]],
        "signals": sigs,
    }
