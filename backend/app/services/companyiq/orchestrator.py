"""CompanyIQ enrichment orchestrator (Brief Section 6.3).

Resolve a query (company name / phone number / CH number) to a canonical identity, check
the cache, fan out to every configured source in parallel with per-source timeouts, merge
into a single payload, cache it, and return it. Failed/absent sources degrade to null
sections — the panel always renders.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy import or_, func

from ...config import settings
from ...models import Call, User
from . import cache
from .sectors import sector_intel_for
from .providers import (companies_house, apollo, hunter, lemlist, google_places,
                        domain_from_url)
from .mastersheet import mastersheet
from .salestracker import sales_tracker

_DISPOSITION = {"completed": "answered", "failed": "no_answer"}


def _to_int(v):
    """Coerce a sheet value like '12' or '1,250' to int; keep ranges/text as-is."""
    if isinstance(v, (int, float)):
        return int(v)
    try:
        return int(str(v).replace(",", "").strip())
    except (ValueError, AttributeError):
        return v


def provider_status() -> dict:
    """Which external sources are live (for the UI to show 'connect a key' hints)."""
    return {
        "companies_house": companies_house.configured,
        "apollo": apollo.configured,
        "hunter": hunter.configured,
        "lemlist": lemlist.configured,
        "google_places": google_places.configured,
        "mastersheet": mastersheet.configured,
        "sales_tracker": sales_tracker.configured,
    }


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def _looks_like_ch_number(q: str) -> bool:
    s = q.strip().upper()
    return bool(re.fullmatch(r"[A-Z]{0,2}\d{6,8}", s)) and any(c.isdigit() for c in s)


def _looks_like_phone(q: str) -> bool:
    d = _digits(q)
    return len(d) >= 7 and not _looks_like_ch_number(q)


# Ingestion sets customer_name to a placeholder ("Unknown Customer") when the real caller
# isn't known. Such values must NEVER drive company resolution — feeding them to Companies
# House returns the same arbitrary top hit for every lookup.
_PLACEHOLDER_NAMES = {"", "unknown", "unknown customer", "unknown caller", "no answer",
                      "voicemail", "n/a", "na", "withheld", "anonymous", "private"}


def _real_name(s: str | None) -> str | None:
    """A usable company/contact name, or None for blanks and ingestion placeholders."""
    s = (s or "").strip()
    return s if s and s.lower() not in _PLACEHOLDER_NAMES else None


# --------------------------------------------------------------- identity + history
def _resolve(db, query: str, phone: str | None = None) -> dict | None:
    """Return {chNumber?, name, domain?, phone?, postcode?} or None if unresolvable.

    ``phone`` is the number the rep is about to dial (optional). It is used to match
    internal call history and is surfaced on the panel as the dialled number.
    """
    q = query.strip()
    # An explicit dial number, or the query itself if it looks like a phone number.
    dial = (phone or "").strip() or (q if _looks_like_phone(q) else "")

    if not q and not dial:
        return None

    # 1. Internal call DB — fastest path; gives us name + domain hint for free.
    call = None
    if dial:
        d = _digits(dial)
        if len(d) >= 7:
            call = (db.query(Call)
                    .filter(or_(func.replace(Call.to_number, " ", "").like(f"%{d[-9:]}%"),
                                func.replace(Call.from_number, " ", "").like(f"%{d[-9:]}%")))
                    .order_by(Call.started_at.desc()).first())
    if call is None and q and not _looks_like_ch_number(q) and not _looks_like_phone(q):
        call = (db.query(Call)
                .filter(or_(Call.customer_name.ilike(f"%{q}%"),
                            Call.customer_company.ilike(f"%{q}%")))
                .order_by(Call.started_at.desc()).first())

    # The company name the rep typed (when it's a name, not a phone/CH number). This always
    # wins over whatever a phone-matched call happens to carry.
    typed_name = q if (q and not _looks_like_phone(q) and not _looks_like_ch_number(q)) else None

    identity = {"name": None, "chNumber": None, "domain": None,
                "phone": dial or None, "postcode": None}
    if call:
        identity["phone"] = dial or call.to_number or call.from_number or None
        comp = call.customer_company or ""
        if "." in comp and " " not in comp:
            identity["domain"] = comp.lower()
        # Prefer the typed name; else the call's real customer_company; never the
        # "Unknown Customer" placeholder (which would resolve everything to one company).
        identity["name"] = typed_name or _real_name(call.customer_company) or _real_name(call.customer_name)
    elif typed_name:
        identity["name"] = typed_name

    # 2. Companies House — canonical identity (live if CH_API_KEY set).
    if q and _looks_like_ch_number(q):
        identity["chNumber"] = q.strip().upper()
        identity["name"] = identity["name"] or q
    elif companies_house.configured and identity["name"]:
        hit = companies_house.search(identity["name"])
        if hit:
            identity["chNumber"] = hit.get("chNumber")
            identity["name"] = identity["name"] or hit.get("name")
            if hit.get("postcode"):
                identity["postcode"] = hit.get("postcode")

    if not (identity["name"] or identity["chNumber"]):
        return None
    return identity


def _call_history(db, identity: dict) -> dict:
    name = identity.get("name")
    phone = identity.get("phone")
    q = db.query(Call)
    conds = []
    if name:
        conds.append(Call.customer_name.ilike(f"%{name}%"))
        conds.append(Call.customer_company.ilike(f"%{name}%"))
    if phone:
        d = _digits(phone)[-9:]
        if d:
            conds.append(func.replace(Call.to_number, " ", "").like(f"%{d}%"))
            conds.append(func.replace(Call.from_number, " ", "").like(f"%{d}%"))
    if not conds:
        return {"totalCalls": 0, "lastCall": None, "log": [], "reachedDM": False}
    calls = (q.filter(or_(*conds)).order_by(Call.started_at.desc()).limit(20).all())
    log = []
    for c in calls:
        host = db.get(User, c.host_id) if c.host_id else None
        log.append({"id": c.id, "repName": host.name if host else "Unknown",
                    "date": c.started_at.isoformat() if c.started_at else None,
                    "durationSec": c.duration_sec,
                    "disposition": _DISPOSITION.get(c.status, c.status),
                    "activityType": c.activity_type})
    no_answer = sum(1 for c in calls if c.status != "completed")
    return {
        "totalCalls": len(calls),
        "lastCall": log[0] if log else None,
        "log": log,
        "coolingOff": no_answer >= 3 and all(c.status != "completed" for c in calls),
        "reachedDM": any(c.status == "completed" for c in calls),
    }


# ------------------------------------------------------------------- enrichment
def enrich_company(db, query: str, phone: str | None = None) -> dict:
    identity = _resolve(db, query, phone)
    if not identity:
        return {"status": "unresolved", "query": query}

    ch_number = identity.get("chNumber")
    dialled = identity.get("phone")
    cache_key = f"companyiq:{ch_number or identity.get('name')}"
    cached = cache.get(cache_key)
    # Call history + dialled number are always recomputed; the rest is cached.
    if cached:
        cached["callHistory"] = _call_history(db, identity)
        cached["dialledNumber"] = dialled
        cached["meta"]["servedFromCache"] = True
        return cached

    domain_hint = identity.get("domain")
    postcode = identity.get("postcode")
    name = identity.get("name")

    # Phase 1 (parallel): CH profile + officers, Google Places, Apollo (org→domain→people),
    # NetSuite. Apollo resolves a domain from the company name when we don't have one.
    with ThreadPoolExecutor(max_workers=6) as ex:
        f_profile = ex.submit(companies_house.profile, ch_number) if ch_number else None
        f_officers = ex.submit(companies_house.officers, ch_number) if ch_number else None
        f_places = ex.submit(google_places.branches, name, postcode) if name else None
        f_apollo = ex.submit(apollo.enrich, domain_hint, name) if (domain_hint or name) else None
        f_orders = ex.submit(sales_tracker.orders_for, name)
        ch_profile = (f_profile.result() if f_profile else None) or {}
        ch_officers = (f_officers.result() if f_officers else None) or []
        places = (f_places.result() if f_places else None) or []
        apollo_data = (f_apollo.result() if f_apollo else None) or {}
        order_history = f_orders.result() or {"available": False}

    # Resolve a canonical web domain from whichever source supplied one.
    domain = (domain_hint or apollo_data.get("domain")
              or domain_from_url(apollo_data.get("website"))
              or next((domain_from_url(p.get("website")) for p in places
                       if p.get("website")), None))

    # Phase 2: Hunter needs the domain we just resolved.
    hunter_contacts = hunter.domain_search(domain) if domain else []

    # ---- master sheet (6th source): fill size/turnover/SIC gaps ----
    sheet = mastersheet.lookup(ch_number=ch_number, name=name) if mastersheet.configured else None

    # Employees: Apollo first, then the master sheet. Turnover: the sheet (curated daily
    # from Apollo/CH) first, then Apollo's rougher estimate.
    employees = employees_meta = None
    if apollo_data.get("employees"):
        employees = apollo_data["employees"]
        employees_meta = {"source": "apollo", "confidence": "medium"}
    elif sheet and sheet.get("employees"):
        employees = _to_int(sheet["employees"])
        employees_meta = {"source": "mastersheet", "confidence": "medium"}

    revenue = revenue_meta = None
    if sheet and sheet.get("revenue"):
        revenue = _to_int(sheet["revenue"])
        revenue_meta = {"source": "mastersheet", "confidence": "medium"}
    elif apollo_data.get("revenue"):
        revenue = apollo_data["revenue"]
        revenue_meta = {"source": "apollo", "confidence": "low"}

    # ---- merge company ----
    addr = ch_profile.get("address") or {}
    sic = ch_profile.get("sicCode") or (sheet.get("sic") if sheet else None)
    company = {
        "name": ch_profile.get("name") or identity.get("name"),
        "chNumber": ch_number,
        "status": ch_profile.get("status"),
        "incorporatedDate": ch_profile.get("incorporatedDate"),
        "sicCode": sic,
        "address": addr,
        "postcode": addr.get("postcode") or postcode,
        "employees": employees,
        "employeesMeta": employees_meta,
        "revenue": revenue,
        "revenueMeta": revenue_meta,
        "enrichment": (sheet.get("extra") if sheet else None),
        "website": apollo_data.get("website") or (f"https://{domain}" if domain else None),
        "domain": domain,
        "phone": apollo_data.get("phone") or ch_profile.get("phone"),
        "branches": places,
        "type": ch_profile.get("type"),
        "sicCodes": ch_profile.get("sicCodes") or ([sic] if sic else []),
        "formerNames": ch_profile.get("formerNames") or [],
        "accounts": ch_profile.get("accounts") or {},
        "confirmationStatement": ch_profile.get("confirmationStatement") or {},
    }

    # ---- merge contacts (Apollo primary, CH officers fallback, Hunter top-up) ----
    contacts = list(apollo_data.get("contacts") or [])
    if not contacts and ch_officers:
        contacts = [{"name": o["name"], "title": o["title"], "email": None,
                     "emailStatus": "estimated", "source": "companies_house",
                     "isPrimary": i == 0, "fromFiling": True,
                     "dob": o.get("dob"), "nationality": o.get("nationality"),
                     "appointedOn": o.get("appointedOn")}
                    for i, o in enumerate(ch_officers)]
    if len(contacts) < 3 and hunter_contacts:
        have = {c.get("email") for c in contacts}
        for h in hunter_contacts:
            if h.get("email") not in have:
                contacts.append(h)

    # ---- outreach: resolve a primary email, then Lemlist ----
    outreach = None
    primary_email = next((c.get("email") for c in contacts if c.get("email")), None)
    if primary_email and lemlist.configured:
        outreach = lemlist.lookup(primary_email)

    sources = []
    if ch_profile:
        sources.append("ch")
    if apollo_data.get("contacts") or apollo_data.get("employees") or apollo_data.get("domain"):
        sources.append("apollo")
    if hunter_contacts:
        sources.append("hunter")
    if outreach:
        sources.append("lemlist")
    if places:
        sources.append("google_places")
    if sheet:
        sources.append("mastersheet")
    if order_history.get("totalOrders"):
        sources.append("sales_tracker")

    payload = {
        "status": "ok",
        "meta": {
            "chNumber": ch_number,
            "resolvedFrom": ("ch_number" if _looks_like_ch_number(query)
                             else "phone" if _looks_like_phone(query) else "name"),
            "cachedAt": datetime.utcnow().isoformat() + "Z",
            "sources": sources,
            "servedFromCache": False,
        },
        "company": company,
        "contacts": contacts,
        "sectorIntel": sector_intel_for(db, sic),
        "outreach": outreach,
        "orderHistory": order_history,
        "providers": provider_status(),
    }

    cache.set(cache_key, payload, settings.companyiq_cache_ttl)
    payload["callHistory"] = _call_history(db, identity)
    payload["dialledNumber"] = dialled
    return payload
