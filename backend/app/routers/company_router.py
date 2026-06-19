"""Company identity / branding — name, logo, phone, address. The logo is shown across the
app; the rest is editable by managers/admins in Settings. Stored as a single Setting row
(`company_profile`); the logo is kept as a small base64 data URL so it persists in the DB
(Railway disk is ephemeral)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_manager
from ..db import get_db
from ..models import User, Setting

router = APIRouter(prefix="/api/company", tags=["company"])

KEY = "company_profile"
MAX_LOGO_CHARS = 750_000   # ~550KB once base64-encoded — keep the logo small


def _profile(db: Session) -> dict:
    row = db.get(Setting, KEY)
    v = row.value if (row and isinstance(row.value, dict)) else {}
    return {"name": v.get("name") or "", "phone": v.get("phone") or "",
            "address": v.get("address") or "", "logo": v.get("logo") or None}


@router.get("")
def get_company(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The company profile, for display anywhere in the app (any signed-in user)."""
    return _profile(db)


@router.put("")
def set_company(body: dict, db: Session = Depends(get_db),
                actor: User = Depends(require_manager)):
    """Set the company name/phone/address/logo (managers & admins). Fields omitted from the
    body are left unchanged; send "logo": null to remove the logo."""
    cur = _profile(db)
    body = body or {}
    name = (body.get("name") if "name" in body else cur["name"]) or ""
    phone = (body.get("phone") if "phone" in body else cur["phone"]) or ""
    address = (body.get("address") if "address" in body else cur["address"]) or ""
    logo = body.get("logo") if "logo" in body else cur["logo"]
    if logo:
        if not isinstance(logo, str) or not logo.startswith("data:image/"):
            raise HTTPException(400, "Logo must be an image (data URL)")
        if len(logo) > MAX_LOGO_CHARS:
            raise HTTPException(413, "Logo is too large — please use an image under ~500KB")
    val = {"name": str(name).strip()[:200], "phone": str(phone).strip()[:60],
           "address": str(address).strip()[:400], "logo": logo or None}
    row = db.get(Setting, KEY)
    if row:
        row.value = val
    else:
        db.add(Setting(key=KEY, value=val))
    db.commit()
    return val
