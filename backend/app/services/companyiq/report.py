"""CompanyIQ AI intel report (Phase 2).

Gathers everything CompanyIQ knows about a company — Companies House profile + filing
history + charges + PSC, Apollo/Hunter contacts, Lemlist outreach, NetSuite status and
internal CallIQ history — and asks Claude to write a BT sales-intel briefing: TL;DR,
priority rating, what-they-do, growth signals, telecom angle, decision-maker guidance,
and a tailored pitch with key angles and watch-outs.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor

from ...config import settings
from ...models import Setting
from . import cache
from .orchestrator import enrich_company
from .providers import companies_house

log = logging.getLogger("calliq.companyiq.report")

REPORT_TTL = 60 * 60 * 12  # 12h — corporate signals change slowly

SYSTEM = (
    "You are a B2B sales intelligence analyst for BT Local Business Oxford & Bucks, a UK "
    "telecom reseller selling BT broadband, leased lines (BTnet), phone/VoIP, EE mobile and "
    "security to businesses across Oxfordshire, Buckinghamshire and Hertfordshire. You turn "
    "raw company data into a punchy, accurate intel briefing a rep reads before dialling. "
    "Be specific and grounded ONLY in the data given — never invent facts, names, figures or "
    "events. If something isn't in the data, omit it. Frame everything toward a telecom/"
    "connectivity sales angle. Reply with ONLY a JSON object, no prose, no code fences."
)

SCHEMA = """Return JSON exactly in this shape:
{
  "priority": {"rating": "HIGH" | "MEDIUM" | "LOW", "reason": "<=15 words why"},
  "tldr": "2-4 sentences: who they are, why now, engagement state",
  "whatTheyDo": "1-3 sentences in plain English",
  "growthSignals": ["recent signal interpreted for sales relevance", ...],
  "telecomSetup": "1-3 sentences on likely current setup and the opportunity",
  "decisionMakers": [{"name": "", "role": "", "guidance": "who to approach and why", "startHere": true|false}],
  "pitch": "3-5 sentence opening a rep could say, in BT's voice",
  "keyAngles": ["specific angle tied to a fact above", ...],
  "watchOuts": ["practical caution for the rep", ...]
}
Rules: 3-6 growthSignals, 2-5 keyAngles, 1-4 watchOuts, mark exactly one decisionMaker startHere:true when contacts exist."""


def _ai_context(db) -> str:
    row = db.get(Setting, "ai_context")
    if row and isinstance(row.value, dict):
        return row.value.get("text", "")
    return ""


def _build_context(payload: dict, officers, timeline, charges, psc) -> str:
    c = payload.get("company") or {}
    parts = [f"COMPANY: {c.get('name')}"]
    if c.get("chNumber"):
        parts.append(f"Companies House: {c['chNumber']} (status: {c.get('status')})")
    if c.get("incorporatedDate"):
        parts.append(f"Incorporated: {c['incorporatedDate']}; type: {c.get('type')}")
    if c.get("sicCodes"):
        parts.append(f"SIC codes: {', '.join(str(s) for s in c['sicCodes'])}")
    addr = c.get("address") or {}
    loc = ", ".join(x for x in [addr.get("locality"), addr.get("postcode")] if x)
    if loc:
        parts.append(f"Registered: {loc}")
    if c.get("formerNames"):
        parts.append("Former names: " + "; ".join(f"{f.get('name')} (to {f.get('ceasedOn')})"
                                                   for f in c["formerNames"]))
    acc = c.get("accounts") or {}
    if acc.get("lastMadeUpTo") or acc.get("nextDue"):
        parts.append(f"Accounts: last made up to {acc.get('lastMadeUpTo')}, next due {acc.get('nextDue')}")
    if c.get("employees"):
        src = (c.get("employeesMeta") or {}).get("source", "")
        parts.append(f"Employees (est.): {c['employees']}{f' [{src}]' if src else ''}")
    if c.get("revenue"):
        src = (c.get("revenueMeta") or {}).get("source", "")
        parts.append(f"Turnover (est.): {c['revenue']}{f' [{src}]' if src else ''}")
    if c.get("enrichment"):
        bits = "; ".join(f"{k}: {v}" for k, v in list(c["enrichment"].items())[:12])
        if bits:
            parts.append(f"Directory enrichment: {bits}")
    if c.get("website"):
        parts.append(f"Website: {c['website']}")
    if c.get("branches"):
        parts.append(f"Branch locations found: {len(c['branches'])} "
                     + "; ".join(b.get("address", "") for b in c["branches"][:5]))

    intel = payload.get("sectorIntel")
    if intel:
        parts.append(f"\nSECTOR ({intel.get('tag')}): {intel.get('brief')}")

    contacts = payload.get("contacts") or []
    if contacts:
        parts.append("\nCONTACTS:")
        for ct in contacts[:6]:
            bits = [ct.get("name"), ct.get("title")]
            if ct.get("email"):
                bits.append(f"email {ct['email']} ({ct.get('emailStatus')})")
            if ct.get("dob"):
                bits.append(f"DOB {ct['dob']}")
            if ct.get("nationality"):
                bits.append(ct["nationality"])
            parts.append("- " + " · ".join(b for b in bits if b))

    if officers:
        parts.append("\nDIRECTORS (Companies House, active):")
        for o in officers[:6]:
            bits = [o.get("name"), o.get("title"),
                    f"appointed {o.get('appointedOn')}" if o.get("appointedOn") else None,
                    f"b. {o.get('dob')}" if o.get("dob") else None, o.get("nationality")]
            parts.append("- " + " · ".join(b for b in bits if b))

    if timeline:
        parts.append("\nRECENT FILINGS (newest first):")
        for t in timeline[:12]:
            parts.append(f"- {t.get('date')}: {t.get('description')} [{t.get('category')}]")

    if charges:
        parts.append("\nCHARGES / DEBT:")
        for ch in charges[:5]:
            parts.append(f"- {ch.get('createdOn')}: {ch.get('classification')} "
                         f"({ch.get('status')}) "
                         + (f"held by {', '.join(ch.get('personsEntitled') or [])}"
                            if ch.get("personsEntitled") else ""))

    if psc:
        parts.append("\nPERSONS WITH SIGNIFICANT CONTROL:")
        for p in psc[:5]:
            parts.append(f"- {p.get('name')} ({p.get('kind')}): "
                         f"{', '.join(n.replace('-', ' ') for n in p.get('natures') or [])}")

    oh = payload.get("orderHistory") or {}
    if oh.get("totalOrders"):
        recent = "; ".join(
            f"{o.get('date')} {o.get('product')} £{o.get('value')} ({o.get('status')})"
            for o in (oh.get("orders") or [])[:5])
        parts.append(f"\nORDER HISTORY (existing customer): {oh['totalOrders']} orders, "
                     f"last {oh.get('lastOrderDate')}. Recent: {recent}")
    else:
        parts.append("\nORDER HISTORY: no previous orders on record (not yet a customer)")
    out = payload.get("outreach")
    if out:
        parts.append(f"LEMLIST outreach: campaign {out.get('campaignName')}, "
                     f"opened={out.get('opened')}, replied={out.get('replied')}")
    else:
        parts.append("LEMLIST outreach: none found")
    hist = payload.get("callHistory") or {}
    if hist.get("totalCalls"):
        last = hist.get("lastCall") or {}
        parts.append(f"CALLIQ history: {hist['totalCalls']} calls; last by "
                     f"{last.get('repName')} on {last.get('date')} ({last.get('disposition')})")
    else:
        parts.append("CALLIQ history: no prior calls (cold)")
    return "\n".join(parts)


def _normalise(report: dict) -> dict:
    rating = str((report.get("priority") or {}).get("rating", "")).upper()
    if rating not in ("HIGH", "MEDIUM", "LOW"):
        rating = "MEDIUM"
    return {
        "priority": {"rating": rating,
                     "reason": (report.get("priority") or {}).get("reason", "")},
        "tldr": report.get("tldr", ""),
        "whatTheyDo": report.get("whatTheyDo", ""),
        "growthSignals": [s for s in (report.get("growthSignals") or []) if s][:6],
        "telecomSetup": report.get("telecomSetup", ""),
        "decisionMakers": (report.get("decisionMakers") or [])[:6],
        "pitch": report.get("pitch", ""),
        "keyAngles": [s for s in (report.get("keyAngles") or []) if s][:5],
        "watchOuts": [s for s in (report.get("watchOuts") or []) if s][:4],
    }


def build_report(db, query: str, phone: str | None = None, refresh: bool = False) -> dict:
    payload = enrich_company(db, query, phone)
    if payload.get("status") == "unresolved":
        return payload

    company = payload.get("company") or {}
    ch_number = company.get("chNumber")

    # Extra Companies House depth (parallel) for the signals timeline.
    officers, timeline, charges, psc = [], [], [], []
    if ch_number and companies_house.configured:
        with ThreadPoolExecutor(max_workers=4) as ex:
            f_off = ex.submit(companies_house.officers, ch_number)
            f_fil = ex.submit(companies_house.filing_history, ch_number)
            f_chg = ex.submit(companies_house.charges, ch_number)
            f_psc = ex.submit(companies_house.psc, ch_number)
            officers = f_off.result() or []
            timeline = f_fil.result() or []
            charges = f_chg.result() or []
            psc = f_psc.result() or []

    result = {
        "status": "ok",
        "company": company,
        "contacts": payload.get("contacts"),
        "sectorIntel": payload.get("sectorIntel"),
        "outreach": payload.get("outreach"),
        "orderHistory": payload.get("orderHistory"),
        "callHistory": payload.get("callHistory"),
        "dialledNumber": payload.get("dialledNumber"),
        "officers": officers,
        "timeline": timeline,
        "charges": charges,
        "psc": psc,
        "meta": payload.get("meta"),
        "report": None,
        "reportError": None,
    }

    cache_key = f"companyiq:report:{ch_number or company.get('name')}"
    if not refresh:
        cached = cache.get(cache_key)
        if cached:
            result["report"] = cached
            result["meta"] = {**(result.get("meta") or {}), "reportCached": True}
            return result

    if not settings.anthropic_api_key:
        result["reportError"] = "AI is not configured (no Anthropic API key)."
        return result

    context = _build_context(payload, officers, timeline, charges, psc)
    bt = _ai_context(db)
    user = (f"BT context: {bt}\n\n" if bt else "") + \
        f"Company data:\n{context}\n\n{SCHEMA}"
    try:
        from ...pipeline.analyzer import _claude, _extract_json
        raw = _claude(SYSTEM, user, settings.claude_report_model, max_tokens=3000)
        report = _normalise(_extract_json(raw))
        cache.set(cache_key, report, REPORT_TTL)
        result["report"] = report
    except Exception as e:
        log.warning("CompanyIQ report generation failed: %s", e)
        result["reportError"] = f"Report generation failed: {str(e)[:200]}"
    return result
