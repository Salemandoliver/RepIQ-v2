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
                       order_to_dict, recompute_totals, set_status, stamp_financial_month)

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
    products = (db.query(OrderProduct).filter(OrderProduct.deleted_at.is_(None),
                OrderProduct.active.is_(True)).order_by(OrderProduct.name).all())
    return {
        "role": role, "canWrite": role in (ADMIN, OPERATIONS), "canDelete": role == ADMIN,
        "statuses": [{"code": c, "label": l, "badge": STATUS_BADGE[c]} for c, l in ORDER_STATUS.items()],
        "acquisition": ACQUISITION_STATUS, "schedule5Check": SCHEDULE5_CHECK,
        "products": [{"id": str(p.id), "name": p.name, "class": p.product_class,
                      "group1": p.product_group1, "group2": p.product_group2,
                      "schedule5Area": p.schedule5_area, "cobra": p.cobra} for p in products],
    }


@router.get("")
def list_orders(status: str | None = None, q: str | None = None, le_code: str | None = None,
                agent_id: int | None = None, date_from: str | None = None, date_to: str | None = None,
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
