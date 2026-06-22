"""Order Entry API (brief §14.2–14.8). Operations + admin write; managers/reps read their scope.

Every write is audited; status changes go through the immutable state machine. Financial figures
(commission £) live in the commission endpoints, gated separately."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_

from ...auth import get_current_user
from ...core.audit import record_audit
from ...db import get_db
from ...models import User
from .models import (ACQUISITION_STATUS, ORDER_STATUS, SCHEDULE5_CHECK, STATUS_BADGE,
                     Order, OrderAgent, OrderDispute, OrderLine, OrderProduct, OrderStatusLog)
from .permissions import order_role, require_write, require_admin, ADMIN, OPERATIONS, MANAGER
from .services import (agent_to_dict, find_or_create_customer, line_to_dict, next_order_number,
                       order_to_dict, recompute_totals, set_status, stamp_financial_month,
                       stamp_week)


def _apply_week(o: Order, body: dict, *, date_changed: bool):
    """Auto-derive the BT week from the order date, honouring an explicit weekNumber override."""
    if "weekNumber" in body:
        v = str(body["weekNumber"]).strip()
        stamp_week(o, override=int(v) if v not in ("", "None") else None)
    elif date_changed:
        stamp_week(o)

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


def _pd(v):
    if not v:
        return None
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise HTTPException(400, f"Bad date: {v}")


_SCALAR = {
    "leAcquisitionStatus": "le_acquisition_status", "mainOrderNumber": "main_order_number",
    "oppId": "opp_id", "volReference": "vol_reference", "orderNotes": "order_notes",
    "cancellationReason": "cancellation_reason", "btNetIssueReason": "bt_net_issue_reason",
    "commissionCrqRef": "commission_crq_ref", "reportingCrqRef": "reporting_crq_ref",
    "deliveryTerms": "delivery_terms", "natureOfTransactionCode": "nature_of_transaction_code",
    "countryOfOrigin": "country_of_origin", "counterpartyVat": "counterparty_vat",
    "currency": "currency",
}
_BOOL = {"hasBeenRejected": "has_been_rejected", "orderCancelled": "order_cancelled",
         "commissionCrqClosed": "commission_crq_closed", "reportingCrqClosed": "reporting_crq_closed",
         "excludeFromEbp": "exclude_from_ebp"}
_DATES = {"orderDate": "order_date", "actualOrderClosedDate": "actual_order_closed_date",
          "cancellationDate": "cancellation_date", "commissionCrqDate": "commission_crq_date",
          "reportingCrqDate": "reporting_crq_date"}


def _apply_fields(db, o: Order, body: dict):
    for k, col in _SCALAR.items():
        if k in body:
            setattr(o, col, (body[k] or None))
    for k, col in _BOOL.items():
        if k in body:
            setattr(o, col, bool(body[k]))
    for k, col in _DATES.items():
        if k in body:
            setattr(o, col, _pd(body[k]))
    if "adminAgentId" in body:
        o.admin_agent_id = body["adminAgentId"] or None
    if "placed" in body:
        was = o.placed
        o.placed = bool(body["placed"])
        if o.placed and not was:
            o.placed_at = datetime.utcnow()
        elif not o.placed:
            o.placed_at = None
    if "companyName" in body or "leCode" in body:
        cust = find_or_create_customer(db, body.get("leCode", o.le_code),
                                       body.get("companyName", o.company_name))
        if cust:
            o.customer_id = cust.id
            o.le_code = cust.le_code
            o.company_name = cust.company_name


def _scope_query(db, user: User, role: str):
    q = db.query(Order).filter(Order.deleted_at.is_(None))
    if role in (ADMIN, OPERATIONS):
        return q
    # manager → team; rep → own. Both keyed off agents / admin_agent.
    agent_orders = db.query(OrderAgent.order_id)
    if role == MANAGER:
        try:
            from ...services.intelligence.team import _team_reps
            ids = [u.id for u in _team_reps(db, None)] or [user.id]
        except Exception:
            ids = [user.id]
    else:
        ids = [user.id]
    agent_orders = agent_orders.filter(OrderAgent.user_id.in_(ids))
    return q.filter(or_(Order.id.in_(agent_orders), Order.admin_agent_id.in_(ids)))


@router.get("/meta")
def meta(db=Depends(get_db), user: User = Depends(get_current_user)):
    role = order_role(db, user)
    from .categories import CATEGORIES, bt_category
    from ...services.salesiq.fincal import (financial_week, weeks_in_financial_year, fy_months,
                                            sales_month, current_sales_month, financial_quarter,
                                            financial_year_start)
    products = (db.query(OrderProduct).filter(OrderProduct.deleted_at.is_(None),
                OrderProduct.active.is_(True)).order_by(OrderProduct.name).all())
    # People for the Sales-Team + Admin-Agent dropdowns (no free-typing → no name typos). Use the
    # preferred/known-as name (short_name) where set, falling back to the full name.
    people_q = db.query(User)
    if hasattr(User, "left_on"):
        people_q = people_q.filter(User.left_on.is_(None))
    people = sorted(({"id": u.id, "name": (u.short_name or u.name), "fullName": u.name,
                      "jobTitle": u.job_title} for u in people_q.all()),
                    key=lambda p: (p["name"] or "").lower())
    cur_week = financial_week()
    weeks = [{"number": w["number"], "weekYear": w["week_year"], "label": w["label"],
              "shortLabel": w["shortLabel"]} for w in weeks_in_financial_year()]
    today = date.today()
    cur_m = current_sales_month(today)
    months = [{"value": f"{y:04d}-{m:02d}", "label": sales_month(y, m)["label"]}
              for (y, m) in fy_months(today)]
    months.reverse()                                              # newest first
    fq = financial_quarter(today)
    fy_year = financial_year_start(today).year
    quarters = [{"value": f"{fy_year}-Q{n}", "label": f"Q{n} {fq['fyLabel']}"} for n in (1, 2, 3, 4)]
    return {
        "role": role, "canWrite": role in (ADMIN, OPERATIONS), "canDelete": role == ADMIN,
        "statuses": [{"code": c, "label": l, "badge": STATUS_BADGE[c]} for c, l in ORDER_STATUS.items()],
        "acquisition": ACQUISITION_STATUS, "schedule5Check": SCHEDULE5_CHECK, "categories": CATEGORIES,
        "people": people,
        "currentWeek": {"number": cur_week["number"], "weekYear": cur_week["week_year"],
                        "label": cur_week["label"]},
        "weeks": weeks, "months": months, "quarters": quarters,
        "currentMonth": f"{cur_m['year']:04d}-{cur_m['month']:02d}",
        "currentQuarter": f"{fy_year}-Q{fq['q']}",
        "products": [{"id": str(p.id), "name": p.name, "class": p.product_class,
                      "group1": p.product_group1, "group2": p.product_group2,
                      "schedule5Area": p.schedule5_area, "cobra": p.cobra,
                      "category": bt_category(p.product_group1, p.product_group2, p.product_class, p.schedule5_area),
                      "rate": (p.extra or {}).get("rate")} for p in products],
    }


def _period_bounds(period: str | None, week: int | None, week_year: int | None,
                   month: str | None, quarter: str | None):
    """(start_date, end_date) for the chosen period filter, or (None, None). period selects which of
    the other params applies: 'week' → week+week_year; 'month' → 'YYYY-MM' sales month; 'quarter' →
    'YYYY-Qn' BT quarter."""
    from ...services.salesiq.fincal import (financial_week_by_number, sales_month, quarter_months,
                                            sales_month_start)
    p = (period or "").lower()
    if p == "week" and week:
        w = financial_week_by_number(int(week), int(week_year) if week_year else date.today().year)
        return w["start"], w["end"]
    if p == "month" and month and len(month) >= 7:
        sm = sales_month(int(month[:4]), int(month[5:7]))
        return sm["start"], sm["end"]
    if p == "quarter" and quarter and "-q" in quarter.lower():
        yr = int(quarter[:4]); qn = int(quarter.lower().split("q")[1])
        # BT FY quarters: Q1 Apr-Jun, Q2 Jul-Sep, Q3 Oct-Dec, Q4 Jan-Mar (next cal year). yr = FY start.
        first_cal_month = {1: 4, 2: 7, 3: 10, 4: 1}[qn]
        ref_year = yr if qn < 4 else yr + 1
        months = quarter_months(date(ref_year, first_cal_month, 15))
        starts = [sales_month_start(y, m) for (y, m) in months]
        last = sales_month(months[-1][0], months[-1][1])
        return min(starts), last["end"]
    return None, None


@router.get("")
def list_orders(status: str | None = None, q: str | None = None, le_code: str | None = None,
                agent_id: int | None = None, date_from: str | None = None, date_to: str | None = None,
                period: str | None = None, week: int | None = None, week_year: int | None = None,
                month: str | None = None, quarter: str | None = None, placed: bool | None = None,
                limit: int = 100, offset: int = 0, db=Depends(get_db),
                user: User = Depends(get_current_user)):
    role = order_role(db, user)
    query = _scope_query(db, user, role)
    if status:
        query = query.filter(Order.status == status.upper())
    if le_code:
        query = query.filter(Order.le_code == le_code)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Order.company_name.ilike(like), Order.order_number.ilike(like),
                                 Order.main_order_number.ilike(like), Order.opp_id.ilike(like)))
    if agent_id:
        sub = db.query(OrderAgent.order_id).filter(OrderAgent.user_id == agent_id)
        query = query.filter(or_(Order.id.in_(sub), Order.admin_agent_id == agent_id))
    if placed is not None:
        query = query.filter(Order.placed.is_(bool(placed)))
    # Period filter (week / month / quarter). A specific week can also match the stored week_number
    # directly (so a manual week override is honoured), else fall back to the order-date range.
    if (period or "").lower() == "week" and week:
        wy = int(week_year) if week_year else None
        cond = Order.week_number == int(week)
        if wy is not None:
            cond = (Order.week_number == int(week)) & (Order.week_year == wy)
        ws, we = _period_bounds("week", week, week_year, None, None)
        query = query.filter(or_(cond, (Order.order_date >= ws) & (Order.order_date <= we)))
    else:
        ps, pe = _period_bounds(period, week, week_year, month, quarter)
        if ps and pe:
            query = query.filter(Order.order_date >= ps, Order.order_date <= pe)
    if date_from:
        query = query.filter(Order.order_date >= _pd(date_from))
    if date_to:
        query = query.filter(Order.order_date <= _pd(date_to))
    total = query.count()
    rows = (query.order_by(Order.order_date.desc(), Order.order_number.desc())
            .offset(max(0, offset)).limit(max(1, min(500, limit))).all())
    return {"total": total, "orders": [order_to_dict(db, o) for o in rows], "role": role}


@router.post("")
def create_order(body: dict, request: Request, db=Depends(get_db), user: User = Depends(get_current_user)):
    require_write(db, user)
    if not (body.get("companyName") or body.get("leCode")):
        raise HTTPException(400, "Customer (company name or LE code) is required")
    o = Order(order_number=body.get("orderNumber") or next_order_number(db),
              order_date=_pd(body.get("orderDate")) or date.today(),
              status=(body.get("status") or "O").upper(), source="manual",
              created_by_id=user.id, company_name="")
    db.add(o)
    _apply_fields(db, o, body)
    stamp_financial_month(o)
    _apply_week(o, body, date_changed=True)
    db.flush()
    db.add(OrderStatusLog(order_id=o.id, from_status=None, to_status=o.status,
                          note="created", changed_by_id=user.id))
    record_audit(db, actor=user, action="CREATE", entity_type="order", entity_id=None,
                 field="order_number", new=o.order_number, request=request)
    db.commit()
    return order_to_dict(db, o, full=True)


@router.get("/{oid}")
def get_order(oid: str, db=Depends(get_db), user: User = Depends(get_current_user)):
    o = db.get(Order, oid)
    if not o or o.deleted_at is not None:
        raise HTTPException(404, "Order not found")
    return order_to_dict(db, o, full=True)


@router.patch("/{oid}")
def update_order(oid: str, body: dict, request: Request, db=Depends(get_db), user: User = Depends(get_current_user)):
    require_write(db, user)
    o = db.get(Order, oid)
    if not o or o.deleted_at is not None:
        raise HTTPException(404, "Order not found")
    if o.locked and order_role(db, user) != ADMIN:
        raise HTTPException(409, "Order is locked (commission month closed) — admin override required")
    _apply_fields(db, o, body)
    if "orderDate" in body:
        stamp_financial_month(o)
    _apply_week(o, body, date_changed="orderDate" in body)
    record_audit(db, actor=user, action="UPDATE", entity_type="order", entity_id=None,
                 field="order_number", new=o.order_number, request=request)
    db.commit()
    return order_to_dict(db, o, full=True)


@router.post("/{oid}/status")
def change_status(oid: str, body: dict, db=Depends(get_db), user: User = Depends(get_current_user)):
    require_write(db, user)
    o = db.get(Order, oid)
    if not o or o.deleted_at is not None:
        raise HTTPException(404, "Order not found")
    set_status(db, o, body.get("status", ""), user, note=body.get("note"))
    db.commit()
    return order_to_dict(db, o, full=True)


@router.get("/{oid}/status-log")
def status_log(oid: str, db=Depends(get_db), user: User = Depends(get_current_user)):
    from .models import OrderStatusLog
    rows = (db.query(OrderStatusLog).filter(OrderStatusLog.order_id == oid)
            .order_by(OrderStatusLog.created_at.desc()).all())
    return {"log": [{"from": r.from_status, "to": r.to_status, "note": r.note,
                     "at": r.created_at.isoformat() if r.created_at else None,
                     "byId": r.changed_by_id} for r in rows]}


@router.delete("/{oid}")
def delete_order(oid: str, request: Request, db=Depends(get_db), user: User = Depends(get_current_user)):
    require_admin(db, user)
    o = db.get(Order, oid)
    if not o:
        raise HTTPException(404, "Order not found")
    o.deleted_at = datetime.utcnow()
    record_audit(db, actor=user, action="DELETE", entity_type="order", entity_id=None,
                 field="order_number", old=o.order_number, request=request)
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------------- line items
def _apply_line(ln: OrderLine, b: dict):
    for k, col in (("item", "item_name"), ("newRen", "new_ren"), ("schedule5Area", "schedule5_area"),
                   ("productGroup1", "product_group1"), ("productGroup2", "product_group2"),
                   ("cobra", "cobra"), ("jobNumber", "job_number"), ("schedule5Check", "schedule5_check"),
                   ("countryOfOrigin", "country_of_origin")):
        if k in b:
            setattr(ln, col, b[k] or None)
    for k, col in (("contractValue", "contract_value"), ("gm", "gm"),
                   ("primarySplitPct", "primary_split_pct"), ("secondSplitPct", "second_split_pct")):
        if k in b:
            setattr(ln, col, float(b[k] or 0))
    if "quantity" in b:
        ln.quantity = int(b["quantity"] or 1)
    if "productId" in b:
        ln.product_id = b["productId"] or None
    if "btCommissionPaid" in b:
        ln.bt_commission_paid = bool(b["btCommissionPaid"])
    if "dateClosed" in b:
        ln.date_closed = _pd(b["dateClosed"])
    if "dateChecked" in b:
        ln.date_checked = _pd(b["dateChecked"])


@router.post("/{oid}/lines")
def add_line(oid: str, body: dict, db=Depends(get_db), user: User = Depends(get_current_user)):
    require_write(db, user)
    o = db.get(Order, oid)
    if not o or o.deleted_at is not None:
        raise HTTPException(404, "Order not found")
    n = max([ln.line_no for ln in o.lines] + [0]) + 1
    ln = OrderLine(order_id=o.id, line_no=n)
    _apply_line(ln, body)
    db.add(ln)
    db.flush()
    recompute_totals(o)
    db.commit()
    return line_to_dict(ln)


@router.patch("/{oid}/lines/{lid}")
def update_line(oid: str, lid: str, body: dict, db=Depends(get_db), user: User = Depends(get_current_user)):
    require_write(db, user)
    ln = db.get(OrderLine, lid)
    if not ln or ln.order_id != oid:
        raise HTTPException(404, "Line not found")
    _apply_line(ln, body)
    db.flush()
    recompute_totals(ln.order)
    db.commit()
    return line_to_dict(ln)


@router.delete("/{oid}/lines/{lid}")
def delete_line(oid: str, lid: str, db=Depends(get_db), user: User = Depends(get_current_user)):
    require_write(db, user)
    ln = db.get(OrderLine, lid)
    if not ln or ln.order_id != oid:
        raise HTTPException(404, "Line not found")
    o = ln.order
    db.delete(ln)
    db.flush()
    recompute_totals(o)
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------------- sales team / agents
@router.put("/{oid}/agents")
def set_agents(oid: str, body: dict, db=Depends(get_db), user: User = Depends(get_current_user)):
    require_write(db, user)
    o = db.get(Order, oid)
    if not o or o.deleted_at is not None:
        raise HTTPException(404, "Order not found")
    for a in list(o.agents):
        db.delete(a)
    db.flush()
    for a in (body.get("agents") or []):
        db.add(OrderAgent(order_id=o.id, user_id=a.get("userId"), agent_name=a.get("name", ""),
                          sales_role=a.get("salesRole"), is_primary=bool(a.get("isPrimary")),
                          split_pct=float(a.get("splitPct") or 0),
                          contribution_pct=float(a.get("contributionPct") or 0)))
    db.flush()
    recompute_totals(o)
    db.commit()
    return {"agents": [agent_to_dict(a) for a in o.agents]}


# ----------------------------------------------------------------- disputes
@router.get("/{oid}/disputes")
def list_disputes(oid: str, db=Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(OrderDispute).filter(OrderDispute.order_id == oid,
                                         OrderDispute.deleted_at.is_(None)).all()
    return {"disputes": [{"id": str(r.id), "type": r.dispute_type, "status": r.status,
                          "summary": r.summary, "resolution": r.resolution, "callId": r.call_id,
                          "createdAt": r.created_at.isoformat() if r.created_at else None} for r in rows]}


@router.post("/{oid}/disputes")
def add_dispute(oid: str, body: dict, db=Depends(get_db), user: User = Depends(get_current_user)):
    require_write(db, user)
    o = db.get(Order, oid)
    if not o or o.deleted_at is not None:
        raise HTTPException(404, "Order not found")
    d = OrderDispute(order_id=o.id, dispute_type=body.get("type"), summary=body.get("summary"),
                     call_id=body.get("callId"), created_by_id=user.id, status="open")
    db.add(d)
    db.commit()
    return {"id": str(d.id)}


@router.patch("/{oid}/disputes/{did}")
def update_dispute(oid: str, did: str, body: dict, db=Depends(get_db), user: User = Depends(get_current_user)):
    require_write(db, user)
    d = db.get(OrderDispute, did)
    if not d or d.order_id != oid:
        raise HTTPException(404, "Dispute not found")
    if "status" in body:
        d.status = body["status"]
        if body["status"] == "resolved":
            d.resolved_at = datetime.utcnow()
    if "resolution" in body:
        d.resolution = body["resolution"]
    if "callId" in body:
        d.call_id = body["callId"]
    db.commit()
    return {"ok": True}
