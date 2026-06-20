"""Product catalogue API. Anyone signed in can read the list (campaigns, pickers); admins manage it."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ...auth import get_current_user
from ...core import rbac
from ...core.audit import record_audit
from ...db import get_db
from ...models import User
from .models import PILLARS, Product

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])


def _require_admin(user: User):
    if rbac.platform_role(user) != rbac.ADMIN:
        raise HTTPException(403, "Admin access required")


def _out(p: Product) -> dict:
    return {"id": str(p.id), "name": p.name, "pillar": p.pillar, "sku": p.sku,
            "keywords": p.keywords, "active": p.active, "sortOrder": p.sort_order, "notes": p.notes}


@router.get("/products")
def list_products(include_inactive: bool = False, db=Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Product).filter(Product.deleted_at.is_(None))
    if not include_inactive:
        q = q.filter(Product.active.is_(True))
    rows = q.order_by(Product.sort_order, Product.name).all()
    return {"products": [_out(p) for p in rows], "pillars": PILLARS}


@router.post("/products")
def create_product(body: dict, request: Request, db=Depends(get_db), user: User = Depends(get_current_user)):
    _require_admin(user)
    if not (body.get("name") or "").strip():
        raise HTTPException(400, "Name is required")
    p = Product(name=body["name"].strip(), pillar=body.get("pillar"), sku=body.get("sku"),
                keywords=body.get("keywords"), notes=body.get("notes"),
                sort_order=int(body.get("sort_order") or 100), active=bool(body.get("active", True)))
    db.add(p)
    record_audit(db, actor=user, action="CREATE", entity_type="product", entity_id=None,
                 field="name", new=p.name, request=request)
    db.commit()
    return _out(p)


@router.patch("/products/{pid}")
def update_product(pid: str, body: dict, request: Request, db=Depends(get_db), user: User = Depends(get_current_user)):
    _require_admin(user)
    p = db.get(Product, pid)
    if not p or p.deleted_at is not None:
        raise HTTPException(404, "Product not found")
    for f in ("name", "pillar", "sku", "keywords", "notes"):
        if f in body:
            setattr(p, f, body[f])
    if "active" in body:
        p.active = bool(body["active"])
    if "sort_order" in body:
        p.sort_order = int(body["sort_order"] or 100)
    record_audit(db, actor=user, action="UPDATE", entity_type="product", entity_id=None,
                 field="name", new=p.name, request=request)
    db.commit()
    return _out(p)


@router.delete("/products/{pid}")
def delete_product(pid: str, request: Request, db=Depends(get_db), user: User = Depends(get_current_user)):
    _require_admin(user)
    p = db.get(Product, pid)
    if not p:
        raise HTTPException(404, "Product not found")
    from datetime import datetime
    p.deleted_at = datetime.utcnow()
    record_audit(db, actor=user, action="DELETE", entity_type="product", entity_id=None,
                 field="name", old=p.name, request=request)
    db.commit()
    return {"ok": True}
