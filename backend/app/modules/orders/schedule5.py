"""Schedule 5 reconciliation (brief §14.9b) — a first-class feature, not a manual process.

BT sends a yearly spreadsheet of every order on their books. Operations upload it; RepIQ auto-matches
each row against its orders (by Main Order Number / OPP ID / company + contract value) and produces a
discrepancy report: matched / value-mismatch / on-Schedule-5-only / in-RepIQ-only. Each discrepancy is
resolved with a logged action, then the reconciliation is signed off.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ...auth import get_current_user
from ...db import get_db
from ...models import User
from ...services.salesiq.fincal import financial_year_start, financial_year_label
from . import imports as erp
from .models import (Order, OrderLine, Schedule5Import, Schedule5Reconciliation, Schedule5Resolution,
                     Schedule5Row)
from .permissions import order_role, ADMIN, OPERATIONS, MANAGER

router = APIRouter(prefix="/api/v1/orders/schedule5", tags=["orders-schedule5"])

_S5_HEADERS = {
    "sales_rep": ["sales rep", "rep"], "date": ["date"], "company": ["company name", "company"],
    "product": ["product"], "contract_value": ["contract value"],
    "order_ref": ["order reference", "order ref", "main order number", "reference"],
    "schedule5_area": ["schedule 5 area", "schedule5 area"],
    "commission_status": ["commission status", "status"],
}


def _idx(headers):
    norm = [erp._norm(h) for h in headers]
    out = {}
    for key, sp in _S5_HEADERS.items():
        for s in sp:
            if s in norm:
                out[key] = norm.index(s)
                break
    return out


def _order_value(o: Order) -> float:
    return round(sum((ln.contract_value or 0) for ln in o.lines if ln.deleted_at is None), 2)


def _match(db: Session, ref, company, value):
    """Find a RepIQ order for a Schedule 5 row. Returns (order, status, detail)."""
    ref = (str(ref).strip() if ref else "")
    order = None
    if ref:
        order = (db.query(Order).filter(Order.deleted_at.is_(None))
                 .filter((Order.main_order_number == ref) | (Order.order_number == ref)
                         | (Order.opp_id == ref)).first())
    if not order and company:
        cands = (db.query(Order).filter(Order.deleted_at.is_(None),
                 Order.company_name.ilike(f"%{str(company).strip()}%")).all())
        if value:
            for c in cands:
                if abs(_order_value(c) - float(value)) <= 1.0:
                    order = c
                    break
        if not order and len(cands) == 1:
            order = cands[0]
    if not order:
        return None, "bt_only", {"reason": "Not found in RepIQ"}
    ov = _order_value(order)
    if value and abs(ov - float(value)) > 1.0:
        return order, "mismatch", {"repiqValue": ov, "btValue": float(value)}
    return order, "matched", {}


@router.post("/import")
async def s5_import(file: UploadFile = File(...), db=Depends(get_db),
                    user: User = Depends(get_current_user)):
    """Upload a BT Schedule 5 file → parse, store rows, auto-reconcile (operations/admin)."""
    if order_role(db, user) not in (ADMIN, OPERATIONS):
        raise HTTPException(403, "Operations/admin only")
    data = await file.read()
    try:
        headers, rows = erp.parse_file(data, file.filename or "schedule5.csv")
    except ValueError as e:
        raise HTTPException(400, str(e))
    idx = _idx(headers)
    imp = Schedule5Import(filename=file.filename or "schedule5", financial_year=financial_year_label(),
                          uploaded_by_id=user.id, row_count=0)
    db.add(imp)
    db.flush()

    def cell(row, key):
        i = idx.get(key)
        return row[i] if (i is not None and i < len(row)) else None

    matched_order_ids, n = set(), 0
    for row in rows:
        ref = cell(row, "order_ref")
        company = cell(row, "company")
        if not ref and not company:
            continue
        value = erp._to_float(cell(row, "contract_value"))
        s5row = Schedule5Row(import_id=imp.id, sales_rep=cell(row, "sales_rep"),
                             row_date=erp._to_date(cell(row, "date")), company_name=company,
                             product=cell(row, "product"), contract_value=value,
                             order_reference=str(ref).strip() if ref else None,
                             schedule5_area=cell(row, "schedule5_area"),
                             commission_status=cell(row, "commission_status"))
        db.add(s5row)
        db.flush()
        order, status, detail = _match(db, ref, company, value)
        if order:
            matched_order_ids.add(order.id)
        db.add(Schedule5Reconciliation(import_id=imp.id, row_id=s5row.id,
                                        order_id=order.id if order else None,
                                        status=status, discrepancy=detail))
        n += 1

    # RepIQ-only: orders in this financial year not seen on Schedule 5
    fy_start = financial_year_start()
    for o in (db.query(Order).filter(Order.deleted_at.is_(None), Order.order_date >= fy_start,
                                     ~Order.status.in_(("M", "N"))).all()):
        if o.id not in matched_order_ids:
            db.add(Schedule5Reconciliation(import_id=imp.id, order_id=o.id, status="repiq_only",
                                           discrepancy={"reason": "In RepIQ, not on Schedule 5"}))
    imp.row_count = n
    db.commit()
    return {"importId": str(imp.id), "rows": n}


@router.get("/imports")
def list_imports(db=Depends(get_db), user: User = Depends(get_current_user)):
    if order_role(db, user) not in (ADMIN, OPERATIONS, MANAGER):
        raise HTTPException(403, "Not permitted")
    rows = db.query(Schedule5Import).filter(Schedule5Import.deleted_at.is_(None)).order_by(
        Schedule5Import.created_at.desc()).all()
    return {"imports": [{"id": str(r.id), "filename": r.filename, "financialYear": r.financial_year,
                         "rows": r.row_count, "signedOff": r.signed_off,
                         "createdAt": r.created_at.isoformat() if r.created_at else None} for r in rows]}


@router.get("/imports/{iid}")
def recon_report(iid: str, db=Depends(get_db), user: User = Depends(get_current_user)):
    if order_role(db, user) not in (ADMIN, OPERATIONS, MANAGER):
        raise HTTPException(403, "Not permitted")
    recs = db.query(Schedule5Reconciliation).filter(Schedule5Reconciliation.import_id == iid).all()
    counts: dict = {}
    items = []
    for r in recs:
        counts[r.status] = counts.get(r.status, 0) + 1
        o = db.get(Order, r.order_id) if r.order_id else None
        row = db.get(Schedule5Row, r.row_id) if r.row_id else None
        items.append({"id": str(r.id), "status": r.status, "discrepancy": r.discrepancy,
                      "order": {"id": str(o.id), "number": o.order_number, "company": o.company_name}
                      if o else None,
                      "schedule5": {"ref": row.order_reference, "company": row.company_name,
                                    "value": row.contract_value, "rep": row.sales_rep} if row else None})
    return {"counts": counts, "items": items}


@router.post("/reconciliation/{rid}/resolve")
def resolve(rid: str, body: dict, db=Depends(get_db), user: User = Depends(get_current_user)):
    if order_role(db, user) not in (ADMIN, OPERATIONS):
        raise HTTPException(403, "Operations/admin only")
    rec = db.get(Schedule5Reconciliation, rid)
    if not rec:
        raise HTTPException(404, "Reconciliation row not found")
    db.add(Schedule5Resolution(reconciliation_id=rec.id, action=body.get("action", "queried_with_bt"),
                               note=body.get("note"), resolved_by_id=user.id))
    db.commit()
    return {"ok": True}


@router.post("/imports/{iid}/sign-off")
def sign_off(iid: str, db=Depends(get_db), user: User = Depends(get_current_user)):
    if order_role(db, user) not in (ADMIN, OPERATIONS):
        raise HTTPException(403, "Operations/admin only")
    imp = db.get(Schedule5Import, iid)
    if not imp:
        raise HTTPException(404, "Import not found")
    imp.signed_off = True
    imp.signed_off_by_id = user.id
    imp.signed_off_at = datetime.utcnow()
    db.commit()
    return {"ok": True}
