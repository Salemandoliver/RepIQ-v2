"""Order Entry — import (ERP Dump), reporting exports, and the BT product catalogue (brief §14.5/14.8).

Kept alongside the live Excel/NetSuite trackers: import is dry-run-then-commit and only brings in the
current financial year (≥ 30 Mar). Admin-gated for import + product config; reports follow order scope.
"""
from __future__ import annotations

import csv
import io
import threading
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from ...auth import get_current_user
from ...db import SessionLocal, get_db
from ...models import User
from . import imports as erp
from .models import ORDER_STATUS, Order, OrderLine, OrderProduct
from .permissions import order_role, require_admin, require_write, ADMIN, OPERATIONS

router = APIRouter(prefix="/api/v1/orders", tags=["orders-admin"])

# Seed products from the live BT data examples (brief §14.5).
_SEED_PRODUCTS = [
    ("Broadband Cross-sell SOADSL/SOGEA/FTTP (excl. Hyperfast) – 5yr", "Broadband", "Broadband Fibre", "SOGEA", "Broadband"),
    ("2021 BT Net – BT Net", "Data Networks & Services", "BT Net", "BT Net", "2021 BT Net – Data and SOV"),
    ("2021 BT Net Security Package New", "Data Networks & Services", "BT Net", "Security", "2021 BT Net – Data and SOV"),
    ("Cloud Voice", "Cloud", "Cloud Voice", "Cloud Voice Volume", "Schedule 5 – Cloud and SOV"),
    ("2021 Cloud Voice Express (Printed)", "Cloud", "Cloud Voice", "Cloud Voice Express", "Schedule 5 – Cloud and SOV"),
    ("BT Mobile New Connections", "Mobile", "Mobile", "Mobile", "Schedule 5 – Mobile and SOV"),
    ("Broadband Superfast", "Broadband", "Broadband Fibre", "FTTP", "Broadband"),
    ("SOV only", "SOV", "SOV", "SOV", "Schedule 5 – SOV only"),
]


def seed_order_products(db) -> None:
    if db.query(OrderProduct.id).first() is not None:
        return
    for name, cls, g1, g2, s5 in _SEED_PRODUCTS:
        db.add(OrderProduct(name=name, product_class=cls, product_group1=g1,
                            product_group2=g2, schedule5_area=s5, active=True))
    db.commit()


@router.post("/import/analyze")
async def import_analyze(file: UploadFile = File(...), db=Depends(get_db),
                         user: User = Depends(get_current_user)):
    """Dry-run an ERP Dump upload — preview what would be imported, nothing written (Operations/admin)."""
    require_write(db, user)
    data = await file.read()
    try:
        return erp.analyze(db, data, file.filename or "upload.csv")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/import/commit")
async def import_commit(file: UploadFile = File(...), replace: bool = False, db=Depends(get_db),
                        user: User = Depends(get_current_user)):
    """Commit an ERP Dump import (≥ FY start). Default is idempotent by SO# (a retry resumes).
    With ``replace=true`` it FIRST wipes all previously-imported orders, then loads the file fresh —
    use this when the new ERP export is the more accurate source of truth. Operations/admin."""
    require_write(db, user)
    data = await file.read()
    try:
        return erp.commit(db, data, file.filename or "upload.csv", user, replace=replace)
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))


# ---- background import with live progress (avoids the HTTP timeout on big replace imports) ----
_IMPORT_JOBS: dict[str, dict] = {}        # jobId -> {total, done, deleted, created, status, error}


@router.post("/import/start")
async def import_start(file: UploadFile = File(...), replace: bool = False, db=Depends(get_db),
                       user: User = Depends(get_current_user)):
    """Kick off an ERP import in the background and return a jobId to poll. Lets the UI show a live
    progress bar instead of a long blocking request (which times out on a full 373-order replace)."""
    require_write(db, user)
    data = await file.read()
    fname = file.filename or "upload.csv"
    uid = user.id
    job_id = uuid.uuid4().hex[:12]
    _IMPORT_JOBS[job_id] = {"total": 0, "done": 0, "deleted": 0, "created": 0,
                            "status": "starting", "error": None, "replace": replace,
                            "startedAt": datetime.utcnow().isoformat() + "Z"}

    def _run():
        s = SessionLocal()
        try:
            u = s.get(User, uid)

            def _prog(**kw):
                _IMPORT_JOBS[job_id].update({k: v for k, v in kw.items() if v is not None})

            r = erp.commit(s, data, fname, u, replace=replace, progress=_prog)
            _IMPORT_JOBS[job_id].update({"status": "done", "created": r["created"],
                                         "deleted": r["deleted"], "done": _IMPORT_JOBS[job_id].get("total", 0)})
        except Exception as e:                              # noqa: BLE001
            try:
                s.rollback()
            except Exception:
                pass
            _IMPORT_JOBS[job_id].update({"status": "error", "error": f"{type(e).__name__}: {str(e)[:300]}"})
        finally:
            s.close()
            # Tidy old jobs so the registry can't grow unbounded.
            if len(_IMPORT_JOBS) > 40:
                for k in list(_IMPORT_JOBS)[:-20]:
                    _IMPORT_JOBS.pop(k, None)

    threading.Thread(target=_run, daemon=True).start()
    return {"jobId": job_id}


@router.get("/import/progress/{job_id}")
def import_progress(job_id: str, db=Depends(get_db), user: User = Depends(get_current_user)):
    j = _IMPORT_JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "Unknown or expired import job")
    return j


@router.post("/import/rate-card")
async def import_rate_card_ep(file: UploadFile = File(...), db=Depends(get_db),
                             user: User = Depends(get_current_user)):
    """Load the yearly BT rate card (.xlsx) into the product catalogue — products, Schedule 5 areas,
    Data/Cloud/Mobile categories and current commission rates (Operations + admin)."""
    require_write(db, user)
    data = await file.read()
    try:
        from .ratecard import import_rate_card
        return import_rate_card(db, data, file.filename or "ratecard.xlsx")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Rate card import failed: {e}")


def _csv_response(headers: list[str], rows: list[list], filename: str) -> StreamingResponse:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    w.writerows(rows)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/report/erp-dump")
def erp_dump_report(db=Depends(get_db), user: User = Depends(get_current_user)):
    """ERP Dump export — one row per order line (brief §14.8). Operations/admin."""
    if order_role(db, user) not in (ADMIN, OPERATIONS):
        raise HTTPException(403, "Operations/admin only")
    headers = ["SO#", "Order Date", "Company Name", "LE", "OPP ID", "Order Status",
               "Product", "Product Group 1", "Product Group 2", "Schedule 5 Area",
               "Contract Value", "Quantity", "GM", "BT Commission Paid", "Schedule 5 Check"]
    rows = []
    q = (db.query(Order, OrderLine).join(OrderLine, OrderLine.order_id == Order.id)
         .filter(Order.deleted_at.is_(None)).order_by(Order.order_date.desc()))
    for o, ln in q.all():
        rows.append([o.order_number, o.order_date.isoformat() if o.order_date else "", o.company_name,
                     o.le_code or "", o.opp_id or "", ORDER_STATUS.get(o.status, o.status),
                     ln.item_name, ln.product_group1 or "", ln.product_group2 or "",
                     ln.schedule5_area or "", ln.contract_value, ln.quantity, ln.gm,
                     "Y" if ln.bt_commission_paid else "N", ln.schedule5_check or ""])
    return _csv_response(headers, rows, "repiq-erp-dump.csv")


@router.get("/report/status-search")
def status_search_export(status: str | None = None, db=Depends(get_db),
                         user: User = Depends(get_current_user)):
    """Sales Order Status search export (brief §14.8)."""
    if order_role(db, user) not in (ADMIN, OPERATIONS):
        raise HTTPException(403, "Operations/admin only")
    headers = ["Date", "Company Name", "LE Code", "SO#", "Main Order Number", "VOL Reference",
               "OPP ID", "Order Status"]
    q = db.query(Order).filter(Order.deleted_at.is_(None))
    if status:
        q = q.filter(Order.status == status.upper())
    rows = [[o.order_date.isoformat() if o.order_date else "", o.company_name, o.le_code or "",
             o.order_number, o.main_order_number or "", o.vol_reference or "", o.opp_id or "",
             ORDER_STATUS.get(o.status, o.status)] for o in q.order_by(Order.order_date.desc()).all()]
    return _csv_response(headers, rows, "repiq-order-status.csv")


# ---- product catalogue admin ----
@router.post("/products")
def create_product(body: dict, db=Depends(get_db), user: User = Depends(get_current_user)):
    require_admin(db, user)
    if not (body.get("name") or "").strip():
        raise HTTPException(400, "Name required")
    p = OrderProduct(name=body["name"].strip(), product_class=body.get("class"),
                     product_group1=body.get("group1"), product_group2=body.get("group2"),
                     schedule5_area=body.get("schedule5Area"), cobra=body.get("cobra"), active=True)
    db.add(p)
    db.commit()
    return {"id": str(p.id)}


@router.delete("/products/{pid}")
def delete_product(pid: str, db=Depends(get_db), user: User = Depends(get_current_user)):
    require_admin(db, user)
    p = db.get(OrderProduct, pid)
    if p:
        p.active = False
        db.commit()
    return {"ok": True}
