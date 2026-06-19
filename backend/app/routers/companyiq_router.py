"""CompanyIQ — in-call company intelligence (Feature Brief v1.0).

Lookup resolves a company by name / phone number / Companies House number and returns a
unified intelligence payload aggregated from every configured source. Sources without a
key degrade gracefully; the panel always renders what is available.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_admin
from ..db import get_db
from ..models import User, Setting
from ..services.companyiq import (enrich_company, provider_status, SECTOR_LIBRARY,
                                  build_report)

router = APIRouter(prefix="/api/companyiq", tags=["companyiq"])


@router.get("/lookup")
def lookup(q: str = Query("", description="Company name, phone or CH number"),
           phone: str = Query("", description="The number being dialled (optional)"),
           db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Resolve a company and return its CompanyIQ intelligence payload.

    Either ``q`` (name / phone / CH number) or ``phone`` (the number being dialled) must
    be supplied. Passing both gives the best result: the name resolves the company and the
    dial number ties it to call history.
    """
    if not q.strip() and not phone.strip():
        return {"status": "unresolved", "query": ""}
    return enrich_company(db, q, phone or None)


@router.get("/report")
def report(q: str = Query("", description="Company name, phone or CH number"),
           phone: str = Query("", description="The number being dialled (optional)"),
           refresh: bool = Query(False, description="Bypass the cached report"),
           db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Full AI sales-intel report: profile + signals timeline + a Claude-written briefing."""
    if not q.strip() and not phone.strip():
        return {"status": "unresolved", "query": ""}
    return build_report(db, q, phone or None, refresh=refresh)


@router.get("/status")
def status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Which external sources are live — drives 'connect a key' hints in the UI."""
    return {"providers": provider_status()}


@router.get("/sheet-debug")
def sheet_debug(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Diagnostics for the master Google Sheet: did it load, how many rows, which
    columns were matched, and any load error. Admin-only."""
    from ..services.companyiq.mastersheet import mastersheet, _state
    mastersheet._load(force=True)
    return {
        "configured": mastersheet.configured,
        "rows": _state.get("n"),
        "matchedColumns": _state.get("cols"),
        "headers": _state.get("headers"),
        "error": _state.get("error"),
    }


@router.get("/sales-debug")
def sales_debug(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Diagnostics for the Sales Tracker workbook: which monthly tabs matched, how many
    confirmed orders each gave, which tabs were skipped, and any load error. Admin-only."""
    from ..services.companyiq.salestracker import sales_tracker, _st
    sales_tracker._load(force=True)
    return {
        "configured": sales_tracker.configured,
        "orderTabs": _st.get("tabs"),
        "totalOrders": _st.get("rows"),
        "perTab": _st.get("perTab"),
        "skippedTabs": _st.get("skipped"),
        "emptyTabSample": _st.get("sample"),
        "error": _st.get("error"),
    }


@router.get("/sectors")
def sectors(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The sector intelligence library (admin-editable copy if one has been saved)."""
    row = db.get(Setting, "companyiq_sectors")
    if row and isinstance(row.value, dict) and row.value.get("cards"):
        return row.value["cards"]
    return SECTOR_LIBRARY


@router.put("/sectors")
def update_sectors(body: dict, db: Session = Depends(get_db),
                   admin: User = Depends(require_admin)):
    """Save an edited sector library (Phase 2 'Sector Intel Admin UI'). No code release."""
    cards = body.get("cards")
    if not isinstance(cards, list):
        return {"ok": False, "error": "Body must be {cards: [...]}"}
    row = db.get(Setting, "companyiq_sectors")
    if row:
        row.value = {"cards": cards}
    else:
        db.add(Setting(key="companyiq_sectors", value={"cards": cards}))
    db.commit()
    return {"ok": True, "count": len(cards)}
