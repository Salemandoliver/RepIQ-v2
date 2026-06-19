"""CompanyIQ — in-call company intelligence orchestrator.

Public surface:
    enrich_company(db, query)      -> CompanyIQ payload dict
    sector_intel_for(db, sic_code) -> sector card dict | None
    SECTOR_LIBRARY                 -> default sector cards (admin-editable copy in Settings)
    provider_status()              -> which external sources are configured
"""
from .orchestrator import enrich_company, provider_status
from .sectors import sector_intel_for, SECTOR_LIBRARY
from .report import build_report

__all__ = ["enrich_company", "provider_status", "sector_intel_for",
           "SECTOR_LIBRARY", "build_report"]
