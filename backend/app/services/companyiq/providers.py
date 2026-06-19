"""External data-source clients for CompanyIQ (Brief Section 6.2).

Every client is independently optional. If its API key is not configured, ``configured``
is False and callers skip it — the panel renders whatever is available (Section 6.6).
All network calls are wrapped so a slow or failing source never blocks the panel.
"""
from __future__ import annotations

import logging
import re

import httpx

from ...config import settings

log = logging.getLogger("calliq.companyiq")

CH_BASE = "https://api.company-information.service.gov.uk"
APOLLO_BASE = "https://api.apollo.io/api/v1"
HUNTER_BASE = "https://api.hunter.io/v2"
LEMLIST_BASE = "https://api.lemlist.com/api"
PLACES_URL = "https://places.googleapis.com/v1/places:searchText"

DECISION_TITLES = ["Managing Director", "Director", "CEO", "Owner", "Founder",
                   "IT Manager", "Operations Manager", "Finance Director"]


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def domain_from_url(url: str | None) -> str | None:
    """Extract a bare domain (no scheme/www/path) from a website URL."""
    if not url:
        return None
    host = re.sub(r"^https?://", "", url.strip().lower()).split("/")[0]
    if host.startswith("www."):
        host = host[4:]
    return host or None


# --------------------------------------------------------------------------- CH
class CompaniesHouse:
    """Core company profile. Free, rate-limited. HTTP Basic — key as username."""

    @property
    def configured(self) -> bool:
        return bool(settings.ch_api_key)

    def _get(self, path: str, params: dict | None = None):
        if not self.configured:
            return None
        try:
            r = httpx.get(f"{CH_BASE}{path}", params=params,
                          auth=(settings.ch_api_key, ""), timeout=3.0)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            log.warning("CH %s failed: %s", path, e)
        return None

    def search(self, query: str) -> dict | None:
        data = self._get("/search/companies", {"q": query, "items_per_page": 3})
        if not data or not data.get("items"):
            return None
        top = data["items"][0]
        return {"chNumber": top.get("company_number"),
                "name": top.get("title"),
                "address": top.get("address_snippet")}

    def profile(self, ch_number: str) -> dict | None:
        data = self._get(f"/company/{ch_number}")
        if not data:
            return None
        addr = data.get("registered_office_address", {}) or {}
        sics = data.get("sic_codes") or []
        accounts = data.get("accounts") or {}
        conf = data.get("confirmation_statement") or {}
        former = [{"name": p.get("name"), "ceasedOn": p.get("ceased_on")}
                  for p in (data.get("previous_company_names") or [])]
        return {
            "name": data.get("company_name"),
            "chNumber": data.get("company_number"),
            "status": (data.get("company_status") or "").lower() or None,
            "incorporatedDate": data.get("date_of_creation"),
            "sicCode": sics[0] if sics else None,
            "sicCodes": sics,
            "address": {
                "line1": addr.get("address_line_1"),
                "line2": addr.get("address_line_2"),
                "locality": addr.get("locality"),
                "postcode": addr.get("postal_code"),
            },
            "type": data.get("type"),
            "formerNames": former,
            "accounts": {"nextDue": accounts.get("next_due"),
                         "lastMadeUpTo": (accounts.get("last_accounts") or {}).get("made_up_to"),
                         "accountsType": (accounts.get("last_accounts") or {}).get("type")},
            "confirmationStatement": {"nextDue": conf.get("next_due"),
                                      "lastMadeUpTo": conf.get("last_made_up_to")},
        }

    @staticmethod
    def _fmt_dob(dob: dict | None) -> str | None:
        if not dob or not dob.get("year"):
            return None
        months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        m = dob.get("month")
        return f"{months[m]} {dob['year']}" if m and 1 <= m <= 12 else str(dob["year"])

    def officers(self, ch_number: str) -> list[dict]:
        data = self._get(f"/company/{ch_number}/officers",
                         {"items_per_page": 20, "order_by": "appointed_on"})
        out = []
        for o in (data or {}).get("items", []):
            if o.get("resigned_on"):
                continue
            out.append({"name": o.get("name"),
                        "title": (o.get("officer_role") or "").replace("-", " ").title(),
                        "appointedOn": o.get("appointed_on"),
                        "dob": self._fmt_dob(o.get("date_of_birth")),
                        "nationality": o.get("nationality"),
                        "occupation": o.get("occupation"),
                        "source": "companies_house"})
        return out[:6]

    def filing_history(self, ch_number: str) -> list[dict]:
        data = self._get(f"/company/{ch_number}/filing-history", {"items_per_page": 20})
        out = []
        for f in (data or {}).get("items", []):
            desc = (f.get("description") or "").replace("-", " ").replace("_", " ").strip()
            out.append({"date": f.get("date"),
                        "category": (f.get("category") or "").replace("-", " "),
                        "type": f.get("type"),
                        "description": desc.capitalize() if desc else f.get("type")})
        return out[:15]

    def charges(self, ch_number: str) -> list[dict]:
        data = self._get(f"/company/{ch_number}/charges")
        out = []
        for c in (data or {}).get("items", []):
            out.append({"status": c.get("status"),
                        "createdOn": c.get("created_on"),
                        "deliveredOn": c.get("delivered_on"),
                        "classification": (c.get("classification") or {}).get("description"),
                        "personsEntitled": [p.get("name") for p in
                                            (c.get("persons_entitled") or [])]})
        return out[:8]

    def psc(self, ch_number: str) -> list[dict]:
        data = self._get(f"/company/{ch_number}/persons-with-significant-control")
        out = []
        for p in (data or {}).get("items", []):
            if p.get("ceased_on"):
                continue
            out.append({"name": p.get("name"),
                        "kind": (p.get("kind") or "").replace("-", " "),
                        "natures": p.get("natures_of_control") or [],
                        "notifiedOn": p.get("notified_on")})
        return out[:6]


# ----------------------------------------------------------------------- Apollo
class Apollo:
    """Decision-maker enrichment by company domain."""

    @property
    def configured(self) -> bool:
        return bool(settings.apollo_api_key)

    def _post(self, path: str, body: dict):
        if not self.configured:
            return None
        try:
            r = httpx.post(f"{APOLLO_BASE}{path}", json=body,
                           headers={"X-Api-Key": settings.apollo_api_key,
                                    "Content-Type": "application/json"}, timeout=3.0)
            if r.status_code == 200:
                return r.json()
            log.warning("Apollo %s -> %s", path, r.status_code)
        except Exception as e:
            log.warning("Apollo %s failed: %s", path, e)
        return None

    def _org_by_domain(self, domain: str) -> dict | None:
        return (self._post("/organizations/enrich", {"domain": domain}) or {}).get("organization")

    def _org_by_name(self, name: str) -> dict | None:
        """Find an organisation by name (used when we have no domain yet)."""
        data = self._post("/mixed_companies/search",
                          {"q_organization_name": name, "per_page": 1}) or {}
        orgs = data.get("organizations") or data.get("accounts") or []
        return orgs[0] if orgs else None

    def _people(self, domain: str) -> list[dict]:
        people = self._post("/mixed_people/search",
                            {"organization_domains": [domain],
                             "person_titles": DECISION_TITLES, "per_page": 5}) or {}
        contacts = []
        for i, p in enumerate(people.get("people", [])):
            contacts.append({
                "name": p.get("name"),
                "title": p.get("title"),
                "email": p.get("email"),
                "emailStatus": "verified" if p.get("email_status") == "verified" else "inferred",
                "linkedin": p.get("linkedin_url"),
                "source": "apollo", "isPrimary": i == 0,
            })
        return contacts

    def enrich(self, domain: str | None = None, name: str | None = None) -> dict | None:
        """Enrich by domain when known, else resolve the org by name first.

        Always returns the resolved ``domain`` so the orchestrator can fan Hunter/Lemlist
        out to it even when the caller only had a company name.
        """
        if not self.configured:
            return None
        org = None
        if domain:
            org = self._org_by_domain(domain)
        elif name:
            org = self._org_by_name(name)
        resolved_domain = domain or (org.get("primary_domain") if org else None) \
            or domain_from_url((org or {}).get("website_url"))
        contacts = self._people(resolved_domain) if resolved_domain else []
        if not org and not contacts and not resolved_domain:
            return None
        return {
            "domain": resolved_domain,
            "employees": org.get("estimated_num_employees") if org else None,
            "revenue": org.get("annual_revenue_printed") if org else None,
            "phone": (org or {}).get("primary_phone", {}).get("number") if org else None,
            "website": org.get("website_url") if org else None,
            "contacts": contacts,
        }


# ----------------------------------------------------------------------- Hunter
class Hunter:
    """Email verification & extra contacts by domain. Conserves credits per Section 6.5."""

    @property
    def configured(self) -> bool:
        return bool(settings.hunter_api_key)

    def domain_search(self, domain: str) -> list[dict]:
        if not self.configured or not domain:
            return []
        try:
            r = httpx.get(f"{HUNTER_BASE}/domain-search",
                          params={"domain": domain, "limit": 5,
                                  "api_key": settings.hunter_api_key}, timeout=2.0)
            if r.status_code != 200:
                return []
            emails = (r.json().get("data") or {}).get("emails", [])
            out = []
            for e in emails:
                name = " ".join(x for x in [e.get("first_name"), e.get("last_name")] if x)
                out.append({"name": name or None, "title": e.get("position"),
                            "email": e.get("value"),
                            "emailStatus": "verified" if (e.get("confidence") or 0) >= 80
                            else "estimated",
                            "source": "hunter", "isPrimary": False})
            return out
        except Exception as e:
            log.warning("Hunter domain-search failed: %s", e)
            return []


# ---------------------------------------------------------------------- Lemlist
class Lemlist:
    """Outreach / sequence status. Basic auth — empty user, API key as password."""

    @property
    def configured(self) -> bool:
        return bool(settings.lemlist_api_key)

    def lookup(self, email: str | None) -> dict | None:
        if not self.configured or not email:
            return None
        try:
            r = httpx.get(f"{LEMLIST_BASE}/leads/{email}",
                          auth=("", settings.lemlist_api_key), timeout=2.0)
            if r.status_code != 200:
                return None
            lead = r.json() or {}
            if not lead:
                return None
            return {
                "inSequence": not lead.get("isPaused", False),
                "campaignName": lead.get("campaignName") or lead.get("campaignId"),
                "lastEmailDate": lead.get("sentAt"),
                "lastEmailSubject": lead.get("subject"),
                "opened": bool(lead.get("openedAt")),
                "clicked": bool(lead.get("clickedAt")),
                "replied": bool(lead.get("repliedAt")),
            }
        except Exception as e:
            log.warning("Lemlist lookup failed: %s", e)
            return None


# ----------------------------------------------------------------- Google Places
class GooglePlaces:
    """Branch / trading location discovery. Cost-controlled per Section 6.5."""

    @property
    def configured(self) -> bool:
        return bool(settings.google_places_key)

    def branches(self, name: str, area: str | None) -> list[dict]:
        if not self.configured or not name:
            return []
        try:
            q = f"{name} {area}".strip() if area else name
            r = httpx.post(PLACES_URL, json={"textQuery": q, "maxResultCount": 3},
                           headers={"X-Goog-Api-Key": settings.google_places_key,
                                    "X-Goog-FieldMask": "places.displayName,"
                                    "places.formattedAddress,places.nationalPhoneNumber,"
                                    "places.websiteUri"},
                           timeout=3.0)
            if r.status_code != 200:
                return []
            out = []
            for p in r.json().get("places", []):
                out.append({"name": (p.get("displayName") or {}).get("text"),
                            "address": p.get("formattedAddress"),
                            "phone": p.get("nationalPhoneNumber"),
                            "website": p.get("websiteUri"), "source": "google_places"})
            return out
        except Exception as e:
            log.warning("Google Places failed: %s", e)
            return []


# Singletons
companies_house = CompaniesHouse()
apollo = Apollo()
hunter = Hunter()
lemlist = Lemlist()
google_places = GooglePlaces()
