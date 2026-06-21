"""Order service — SO numbering, the status state machine, totals/GM recompute, financial-month
stamping, agent contribution maths, and role-aware serialisation (brief §14)."""
from __future__ import annotations

import re
from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from ...models import User
from ...services.salesiq.fincal import financial_month_key
from .models import (ORDER_STATUS, STATUS_BADGE, Customer, Order, OrderAgent, OrderLine,
                     OrderStatusLog)

_SO_FLOOR = 8358          # continue the live NetSuite sequence (brief example SO8358)


def next_order_number(db: Session) -> str:
    """Next sequential SO number (e.g. SO8359), continuing the existing sequence."""
    mx = _SO_FLOOR
    for (num,) in db.query(Order.order_number).all():
        m = re.search(r"(\d+)", num or "")
        if m:
            mx = max(mx, int(m.group(1)))
    return f"SO{mx + 1}"


def find_or_create_customer(db: Session, le_code: str | None, company_name: str) -> Customer | None:
    company_name = (company_name or "").strip()
    le_code = (le_code or "").strip() or None
    if not company_name and not le_code:
        return None
    q = db.query(Customer).filter(Customer.deleted_at.is_(None))
    cust = None
    if le_code:
        cust = q.filter(Customer.le_code == le_code).first()
    if not cust and company_name:
        cust = q.filter(func.lower(Customer.company_name) == company_name.lower()).first()
    if cust:
        if le_code and not cust.le_code:
            cust.le_code = le_code
        return cust
    cust = Customer(le_code=le_code, company_name=company_name or le_code)
    db.add(cust)
    db.flush()
    return cust


def recompute_totals(order: Order) -> None:
    subtotal = sum((ln.gm or 0.0) for ln in order.lines if ln.deleted_at is None)
    order.subtotal = round(subtotal, 2)
    order.total = round(subtotal, 2)
    for a in order.agents:
        a.contribution_amount = round(order.total * (a.contribution_pct or 0) / 100.0, 2)


def stamp_financial_month(order: Order) -> None:
    if order.order_date:
        order.financial_month = financial_month_key(order.order_date)


def set_status(db: Session, order: Order, new_status: str, user: User | None,
               note: str | None = None) -> None:
    """Apply a status transition + write the immutable status-log entry (brief §14.3)."""
    new_status = (new_status or "").upper()
    if new_status not in ORDER_STATUS:
        from fastapi import HTTPException
        raise HTTPException(400, f"Unknown order status '{new_status}'")
    if order.status == new_status:
        return
    db.add(OrderStatusLog(order_id=order.id, from_status=order.status, to_status=new_status,
                          note=note, changed_by_id=user.id if user else None))
    order.status = new_status
    order.status_changed_at = datetime.utcnow()
    if new_status in ("M",):
        order.order_cancelled = True


# ----------------------------------------------------------------- serialisation
def _user_name(db: Session, uid: int | None) -> str | None:
    if not uid:
        return None
    u = db.get(User, uid)
    return (u.short_name or u.name) if u else None


def line_to_dict(ln: OrderLine) -> dict:
    return {
        "id": str(ln.id), "lineNo": ln.line_no, "productId": str(ln.product_id) if ln.product_id else None,
        "item": ln.item_name, "contractValue": ln.contract_value, "quantity": ln.quantity,
        "newRen": ln.new_ren, "schedule5Area": ln.schedule5_area, "productGroup1": ln.product_group1,
        "productGroup2": ln.product_group2, "cobra": ln.cobra, "gm": ln.gm, "jobNumber": ln.job_number,
        "primarySplitPct": ln.primary_split_pct, "secondSplitPct": ln.second_split_pct,
        "dateClosed": ln.date_closed.isoformat() if ln.date_closed else None,
        "btCommissionPaid": ln.bt_commission_paid, "schedule5Check": ln.schedule5_check,
        "dateChecked": ln.date_checked.isoformat() if ln.date_checked else None,
        "countryOfOrigin": ln.country_of_origin,
    }


def agent_to_dict(a: OrderAgent) -> dict:
    return {
        "id": str(a.id), "userId": a.user_id, "name": a.agent_name, "salesRole": a.sales_role,
        "isPrimary": a.is_primary, "splitPct": a.split_pct, "contributionPct": a.contribution_pct,
        "contributionAmount": a.contribution_amount,
    }


def order_to_dict(db: Session, o: Order, *, full: bool = False) -> dict:
    d = {
        "id": str(o.id), "orderNumber": o.order_number,
        "orderDate": o.order_date.isoformat() if o.order_date else None,
        "financialMonth": o.financial_month.isoformat() if o.financial_month else None,
        "leCode": o.le_code, "companyName": o.company_name,
        "leAcquisitionStatus": o.le_acquisition_status,
        "status": o.status, "statusLabel": ORDER_STATUS.get(o.status, o.status),
        "badge": STATUS_BADGE.get(o.status, o.status),
        "statusChangedAt": o.status_changed_at.isoformat() if o.status_changed_at else None,
        "mainOrderNumber": o.main_order_number, "oppId": o.opp_id, "volReference": o.vol_reference,
        "adminAgentId": o.admin_agent_id, "adminAgentName": _user_name(db, o.admin_agent_id),
        "hasBeenRejected": o.has_been_rejected, "orderCancelled": o.order_cancelled,
        "subtotal": o.subtotal, "total": o.total, "currency": o.currency, "locked": o.locked,
        "source": o.source,
    }
    if not full:
        return d
    d.update({
        "orderNotes": o.order_notes,
        "actualOrderClosedDate": o.actual_order_closed_date.isoformat() if o.actual_order_closed_date else None,
        "cancellationReason": o.cancellation_reason,
        "cancellationDate": o.cancellation_date.isoformat() if o.cancellation_date else None,
        "btNetIssueReason": o.bt_net_issue_reason,
        "commissionCrqRef": o.commission_crq_ref,
        "commissionCrqDate": o.commission_crq_date.isoformat() if o.commission_crq_date else None,
        "commissionCrqClosed": o.commission_crq_closed,
        "reportingCrqRef": o.reporting_crq_ref,
        "reportingCrqDate": o.reporting_crq_date.isoformat() if o.reporting_crq_date else None,
        "reportingCrqClosed": o.reporting_crq_closed,
        "excludeFromEbp": o.exclude_from_ebp, "deliveryTerms": o.delivery_terms,
        "natureOfTransactionCode": o.nature_of_transaction_code,
        "countryOfOrigin": o.country_of_origin, "counterpartyVat": o.counterparty_vat,
        "subsidiary": o.subsidiary,
        "lines": [line_to_dict(ln) for ln in sorted(o.lines, key=lambda x: x.line_no) if ln.deleted_at is None],
        "agents": [agent_to_dict(a) for a in o.agents if a.deleted_at is None],
    })
    return d
