"""Commission engine (brief §14.9c) — pay plans → monthly run → per-line calculation with splits and
exclusions → per-rep statements → admin approve/lock.

Calculation per eligible order line:
  line commission = GM × (pay-plan rate for that product) , then allocated across the order's agents
  by their contribution %, then a rep-level accelerator applied if they're over target.
Excluded: cancelled (M) + non-commissionable (N) orders, and lines where BT hasn't paid
(bt_commission_paid = false) — commission is only counted once received.
Historical runs always use the pay plan that was active on the month (effective_date).
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...auth import get_current_user
from ...db import get_db
from ...models import User
from .models import (CommissionRun, CommissionStatement, Order, OrderAgent, OrderLine, OrderTarget,
                     PayPlan)
from .permissions import order_role, ADMIN, OPERATIONS, MANAGER

router = APIRouter(prefix="/api/v1/orders/commission", tags=["orders-commission"])


# ----------------------------------------------------------------- calculation
def _rate_for(line: OrderLine, plan_cfg: dict) -> float:
    """Most-specific matching rate %, else the plan default."""
    best, best_score = plan_cfg.get("default_rate_pct", 0.0), -1
    for r in (plan_cfg.get("rates") or []):
        m = r.get("match") or {}
        score, ok = 0, True
        for key, col in (("class", line.schedule5_area), ("group1", line.product_group1),
                         ("group2", line.product_group2), ("schedule5", line.schedule5_area)):
            if m.get(key):
                if (col or "").lower() == str(m[key]).lower():
                    score += 1
                else:
                    ok = False
                    break
        if ok and score > best_score:
            best, best_score = float(r.get("rate_pct", 0)), score
    return best


def _active_plan(db: Session, on: date) -> PayPlan | None:
    return (db.query(PayPlan).filter(PayPlan.deleted_at.is_(None), PayPlan.active.is_(True),
                                     PayPlan.effective_date <= on)
            .order_by(PayPlan.effective_date.desc()).first())


def _agent_allocation(order: Order) -> list[tuple]:
    """[(user_id, name, fraction)] — how a line's commission splits across the order's agents."""
    agents = [a for a in order.agents if a.deleted_at is None]
    total = sum((a.contribution_pct or 0) for a in agents)
    if agents and total > 0:
        return [(a.user_id, a.agent_name, (a.contribution_pct or 0) / total) for a in agents]
    primary = next((a for a in agents if a.is_primary), agents[0] if agents else None)
    if primary:
        return [(primary.user_id, primary.agent_name, 1.0)]
    return [(None, "Unassigned", 1.0)]


def calculate(db: Session, fin_month: date, plan: PayPlan | None) -> dict:
    """Compute statements per rep for a financial month. Returns {statements, totals}."""
    cfg = (plan.config if plan else {}) or {}
    min_gm = float(cfg.get("min_order_gm", 0) or 0)
    orders = (db.query(Order).filter(Order.deleted_at.is_(None), Order.financial_month == fin_month,
                                     ~Order.status.in_(("M", "N"))).all())
    per_rep: dict = {}
    for o in orders:
        alloc = _agent_allocation(o)
        for ln in o.lines:
            if ln.deleted_at is not None or not ln.bt_commission_paid:
                continue
            # We pay on what BT actually paid us — the Cobra GM — when it's been entered (admin);
            # otherwise fall back to the order's GM.
            gm = (ln.cobra_gm if ln.cobra_gm is not None else ln.gm) or 0.0
            if gm < min_gm:
                continue
            line_comm = gm * _rate_for(ln, cfg) / 100.0
            for uid, name, frac in alloc:
                key = uid if uid is not None else f"name:{name}"
                r = per_rep.setdefault(key, {"userId": uid, "name": name, "gross": 0.0, "gm": 0.0,
                                             "orders": set(), "lines": []})
                share = line_comm * frac
                r["gross"] += share
                r["gm"] += gm * frac
                r["orders"].add(o.id)
                r["lines"].append({"order": o.order_number, "company": o.company_name,
                                   "item": ln.item_name, "gm": round(gm * frac, 2),
                                   "commission": round(share, 2)})
    # rep-level accelerator vs monthly target
    accel = cfg.get("accelerators") or []
    statements = []
    for key, r in per_rep.items():
        gross = r["gross"]
        net = gross
        if r["userId"] and accel:
            tgt = db.query(OrderTarget).filter(OrderTarget.user_id == r["userId"],
                                               OrderTarget.financial_month == fin_month).first()
            if tgt and tgt.revenue_target:
                pct = 100.0 * r["gm"] / tgt.revenue_target
                mult = 1.0
                for a in sorted(accel, key=lambda x: x.get("from_pct", 0)):
                    if pct >= a.get("from_pct", 0):
                        mult = a.get("multiplier", 1.0)
                net = gross * mult
        statements.append({"userId": r["userId"], "name": r["name"],
                           "gross": round(gross, 2), "net": round(net, 2),
                           "orderCount": len(r["orders"]), "lines": r["lines"]})
    statements.sort(key=lambda s: -s["net"])
    totals = {"gross": round(sum(s["gross"] for s in statements), 2),
              "net": round(sum(s["net"] for s in statements), 2),
              "reps": len(statements)}
    return {"statements": statements, "totals": totals}


# ----------------------------------------------------------------- endpoints
def _require_ops(db, user):
    if order_role(db, user) not in (ADMIN, OPERATIONS):
        raise HTTPException(403, "Operations/admin only")


def _require_admin(db, user):
    if order_role(db, user) != ADMIN:
        raise HTTPException(403, "Admin only")


@router.get("/pay-plans")
def list_pay_plans(db=Depends(get_db), user: User = Depends(get_current_user)):
    _require_ops(db, user)
    rows = db.query(PayPlan).filter(PayPlan.deleted_at.is_(None)).order_by(PayPlan.effective_date.desc()).all()
    return {"payPlans": [{"id": str(p.id), "name": p.name,
                          "effectiveDate": p.effective_date.isoformat(), "active": p.active,
                          "config": p.config} for p in rows]}


@router.post("/pay-plans")
def create_pay_plan(body: dict, db=Depends(get_db), user: User = Depends(get_current_user)):
    _require_admin(db, user)
    from datetime import datetime as _dt
    eff = body.get("effectiveDate")
    p = PayPlan(name=body.get("name", "Pay plan"),
                effective_date=_dt.strptime(eff[:10], "%Y-%m-%d").date() if eff else date.today(),
                config=body.get("config") or {}, active=bool(body.get("active", True)),
                created_by_id=user.id)
    db.add(p)
    db.commit()
    return {"id": str(p.id)}


@router.post("/runs")
def run_commission(body: dict, db=Depends(get_db), user: User = Depends(get_current_user)):
    """Calculate a monthly commission run + statements (operations/admin)."""
    _require_ops(db, user)
    from datetime import datetime as _dt
    fm = body.get("financialMonth")
    if not fm:
        raise HTTPException(400, "financialMonth (YYYY-MM-DD, the BT month key) is required")
    fin_month = _dt.strptime(fm[:10], "%Y-%m-%d").date()
    plan = db.get(PayPlan, body["payPlanId"]) if body.get("payPlanId") else _active_plan(db, fin_month)
    result = calculate(db, fin_month, plan)
    run = CommissionRun(financial_month=fin_month, status="calculated",
                        pay_plan_id=plan.id if plan else None, totals=result["totals"],
                        created_by_id=user.id)
    db.add(run)
    db.flush()
    for s in result["statements"]:
        db.add(CommissionStatement(run_id=run.id, user_id=s["userId"], rep_name=s["name"],
                                   gross_commission=s["gross"], net_commission=s["net"],
                                   order_count=s["orderCount"], lines=s["lines"], status="draft"))
    db.commit()
    return {"runId": str(run.id), "totals": result["totals"], "statements": result["statements"]}


@router.get("/runs")
def list_runs(db=Depends(get_db), user: User = Depends(get_current_user)):
    _require_ops(db, user)
    rows = db.query(CommissionRun).filter(CommissionRun.deleted_at.is_(None)).order_by(
        CommissionRun.financial_month.desc()).all()
    return {"runs": [{"id": str(r.id), "financialMonth": r.financial_month.isoformat(),
                      "status": r.status, "totals": r.totals,
                      "lockedAt": r.locked_at.isoformat() if r.locked_at else None} for r in rows]}


@router.get("/runs/{rid}")
def run_statements(rid: str, db=Depends(get_db), user: User = Depends(get_current_user)):
    role = order_role(db, user)
    run = db.get(CommissionRun, rid)
    if not run:
        raise HTTPException(404, "Run not found")
    q = db.query(CommissionStatement).filter(CommissionStatement.run_id == rid)
    if role == MANAGER:
        try:
            from ...services.intelligence.team import _team_reps
            ids = [u.id for u in _team_reps(db, None)]
            q = q.filter(CommissionStatement.user_id.in_(ids))
        except Exception:
            pass
    elif role not in (ADMIN, OPERATIONS):
        q = q.filter(CommissionStatement.user_id == user.id)
    stmts = [{"id": str(s.id), "userId": s.user_id, "name": s.rep_name, "gross": s.gross_commission,
              "net": s.net_commission, "orderCount": s.order_count, "lines": s.lines,
              "status": s.status} for s in q.all()]
    return {"run": {"id": str(run.id), "financialMonth": run.financial_month.isoformat(),
                    "status": run.status, "totals": run.totals}, "statements": stmts}


@router.post("/runs/{rid}/approve")
def approve_run(rid: str, db=Depends(get_db), user: User = Depends(get_current_user)):
    """Admin approves + locks the run; orders in that month are locked from edits (brief §14.9c)."""
    _require_admin(db, user)
    run = db.get(CommissionRun, rid)
    if not run:
        raise HTTPException(404, "Run not found")
    run.status = "locked"
    run.approved_by_id = user.id
    run.locked_at = datetime.utcnow()
    db.query(Order).filter(Order.financial_month == run.financial_month).update(
        {Order.locked: True}, synchronize_session=False)
    db.commit()
    return {"ok": True, "status": run.status}
