"""Sector Intelligence Library (Feature Brief Section 03).

Each UK SIC 2007 division maps to a curated telecom sales angle — 2-4 sentences a rep
can use the moment they dial. Maintained centrally; an admin-editable copy is stored in
the Settings table under key ``companyiq_sectors`` so management can update briefings
without a code release (Phase 2 'Sector Intel Admin UI').
"""
from __future__ import annotations

# tag, brief, and the 2-digit SIC division prefixes that map to it.
SECTOR_LIBRARY: list[dict] = [
    {
        "tag": "Education", "color": "#16a34a",
        "divisions": ["85"],
        "brief": "Government regulation requires 100% uptime and built-in resilience for "
                 "schools and colleges. Ofsted now assesses digital infrastructure "
                 "readiness. Fibre with automatic failover is both a compliance win and a "
                 "safeguarding argument — not just a product pitch.",
    },
    {
        "tag": "Hospitality", "color": "#f59e0b",
        "divisions": ["55", "56"],
        "brief": "FIFA World Cup 2026 — venues, hotels, and bars need guaranteed high-speed "
                 "broadband to handle simultaneous streaming, card payments, and peak guest "
                 "Wi-Fi demand. A single night of downtime during a match can cost "
                 "thousands. Frame broadband as event insurance, not infrastructure.",
    },
    {
        "tag": "Healthcare", "color": "#ef4444",
        "divisions": ["86", "87"],
        "brief": "CQC inspections increasingly assess digital infrastructure. VOIP "
                 "reliability and call recording are now expected for GP practices, care "
                 "homes, and dental surgeries. System downtime affects patient safety — "
                 "uptime SLAs and failover are mandatory requirements, not upgrades.",
    },
    {
        "tag": "Construction", "color": "#eab308",
        "divisions": ["41", "42", "43"],
        "brief": "Remote site and multi-location connectivity is the defining pain point. "
                 "Fixed wireless, 4G/5G backup, and mobile data bundles are consistent "
                 "gaps. Companies manage multiple temporary and permanent sites — a single "
                 "provider with flexible contracts is a major operational saving.",
    },
    {
        "tag": "Retail", "color": "#3b82f6",
        "divisions": ["47"],
        "brief": "Card payment systems go down when broadband does — and that means lost "
                 "revenue immediately. Multi-site retailers are managing separate telecom "
                 "contracts per location. A consolidated single-provider contract reduces "
                 "admin overhead and usually reduces cost.",
    },
    {
        "tag": "Legal", "color": "#9333ea",
        "divisions": ["69"],
        "brief": "SRA regulations require all client communications to be retained and "
                 "accessible. Call recording and secure VOIP are compliance requirements, "
                 "not optional. Law firms are moving off legacy PBX and looking for modern "
                 "hosted telephony that integrates with their case management systems.",
    },
    {
        "tag": "Financial Services", "color": "#4f46e5",
        "divisions": ["64", "65", "66"],
        "brief": "FCA mandates call recording for all customer-facing communications. FCA "
                 "compliance audits increasingly cover digital infrastructure resilience. "
                 "Outages create regulatory exposure, not just operational inconvenience — "
                 "uptime SLAs become compliance documents.",
    },
    {
        "tag": "Property", "color": "#14b8a6",
        "divisions": ["68"],
        "brief": "Estate agents and letting agencies manage multiple offices and a mobile "
                 "workforce. Unified communications — VOIP, mobile, broadband — under a "
                 "single provider is the core pitch. Click-to-call CRM integration is an "
                 "increasingly common requirement and a strong differentiator.",
    },
    {
        "tag": "Transport & Logistics", "color": "#0ea5e9",
        "divisions": ["49", "50", "51", "52", "53"],
        "brief": "Fleet tracking, driver comms, depot connectivity and mobile data plans "
                 "are the recurring needs. Multi-depot operations benefit from a single "
                 "provider covering fixed broadband and mobile across every site and "
                 "vehicle.",
    },
    {
        "tag": "Manufacturing", "color": "#64748b",
        "divisions": ["10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20",
                      "21", "22", "23", "24", "25", "26", "27", "28", "29", "30", "31",
                      "32", "33"],
        "brief": "Factory-floor connectivity, IoT readiness, multi-site WAN and legacy PBX "
                 "replacement are the openings. Reliable connectivity underpins production "
                 "systems, so resilience and a single accountable provider are compelling.",
    },
    {
        "tag": "Automotive", "color": "#dc2626",
        "divisions": ["45"],
        "brief": "Showroom Wi-Fi, DVLA/HMRC portal uptime dependency, and mobile data for "
                 "mobile technicians drive the conversation. Dealerships and garages need "
                 "guaranteed uptime for trade portals plus mobile coverage on the road.",
    },
    {
        "tag": "Agriculture", "color": "#65a30d",
        "divisions": ["01", "02", "03"],
        "brief": "Rural connectivity gaps are the headline issue — Starlink vs fibre, mobile "
                 "signal boosters, and grant-eligible upgrades. Many rural businesses "
                 "qualify for funded connectivity improvements worth leading with.",
    },
    {
        "tag": "Charity / Not-for-Profit", "color": "#7c3aed",
        "divisions": ["94", "88"],
        "brief": "Budget sensitivity is paramount; grant-funded upgrades and broadband as "
                 "infrastructure-grant eligibility are the angles. Position connectivity as "
                 "a fundable investment, not an operating cost.",
    },
]

# Build a fast division -> card lookup (first match wins, ordering above is priority).
_DIVISION_INDEX: dict[str, dict] = {}
for _card in SECTOR_LIBRARY:
    for _div in _card["divisions"]:
        _DIVISION_INDEX.setdefault(_div, _card)


def _match_card(sic_code: str | None, library: list[dict]) -> dict | None:
    if not sic_code:
        return None
    div = "".join(c for c in str(sic_code) if c.isdigit())[:2]
    if not div:
        return None
    for card in library:
        if div in card.get("divisions", []):
            return card
    return None


def sector_intel_for(db, sic_code: str | None) -> dict | None:
    """Return the sector card for a SIC code, using the admin-editable library if present.

    ``db`` may be None (falls back to the built-in library).
    """
    library = SECTOR_LIBRARY
    if db is not None:
        try:
            from ...models import Setting
            row = db.get(Setting, "companyiq_sectors")
            if row and isinstance(row.value, dict) and row.value.get("cards"):
                library = row.value["cards"]
        except Exception:
            library = SECTOR_LIBRARY
    card = _match_card(sic_code, library)
    if not card:
        return None
    return {"tag": card.get("tag"), "brief": card.get("brief"),
            "color": card.get("color", "#6b7280"),
            "updatedAt": card.get("updatedAt")}
