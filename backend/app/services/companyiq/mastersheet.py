"""Master companies directory — Google Sheet source for CompanyIQ.

A single Sheet (~37k rows, refreshed daily from Apollo/Companies House) acts as a fast
local fallback for employees / revenue / SIC and any extra enrichment the live APIs miss.
The whole sheet is loaded once and indexed in memory (by CH number and by normalised name),
refreshed on a TTL. All failures degrade to None — the panel never blocks on it.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time

from ...config import settings

log = logging.getLogger("calliq.companyiq.mastersheet")

_lock = threading.Lock()
_state = {"loaded_at": 0.0, "by_ch": {}, "by_name": {}, "cols": {}, "n": 0,
         "headers": [], "error": None}

_SUFFIX = re.compile(r"\b(ltd|limited|plc|llp|llc|inc|co|company|group|holdings|uk|the)\b")


def _norm_name(s: str | None) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    s = _SUFFIX.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def _norm_ch(s: str | None) -> str:
    s = re.sub(r"\s", "", (s or "").upper())
    # Companies House numbers are 8 chars with leading zeros, but sheets often store
    # numeric ones without them — strip leading zeros so both sides match.
    return s.lstrip("0") if s.isdigit() else s


def creds_available() -> bool:
    return bool(settings.google_service_account_json) or \
        os.path.exists(settings.google_service_account_file)


def build_gspread_client():
    """Authorised gspread client shared by all Google-Sheet sources."""
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    if settings.google_service_account_json:
        raw = settings.google_service_account_json.strip()
        if not raw.startswith("{"):
            import base64
            raw = base64.b64decode(raw).decode("utf-8")
        info = json.loads(raw, strict=False)
        creds = Credentials.from_service_account_info(info, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file(
            settings.google_service_account_file, scopes=scopes)
    return gspread.authorize(creds)


def pick_col(headers, exact=(), contains=()) -> str | None:
    """Match a column: exact (case-insensitive) header names first, then substrings."""
    low = {h: str(h).strip().lower() for h in headers}
    for e in exact:
        el = e.lower()
        for h in headers:
            if low[h] == el:
                return h
    for kw in contains:
        for h in headers:
            if kw in low[h]:
                return h
    return None


class MasterSheet:
    @property
    def configured(self) -> bool:
        return bool(settings.master_sheet_id) and creds_available()

    def _client(self):
        return build_gspread_client()

    @staticmethod
    def _pick(headers, exact=(), contains=()) -> str | None:
        return pick_col(headers, exact, contains)

    def _load(self, force: bool = False) -> None:
        with _lock:
            fresh = _state["n"] and (time.time() - _state["loaded_at"] < settings.mastersheet_ttl)
            if fresh and not force:
                return
            try:
                gc = self._client()
                sh = gc.open_by_key(settings.master_sheet_id)
                ws = (sh.worksheet(settings.master_sheet_tab)
                      if settings.master_sheet_tab else sh.sheet1)
                # get_all_values (not get_all_records) so blank/duplicate header cells
                # don't blow up — we build the row dicts ourselves below.
                values = ws.get_all_values()
            except Exception as e:
                _state["error"] = f"{type(e).__name__}: {str(e)[:300]}"
                log.warning("MasterSheet load failed: %s", e)
                return
            if not values or len(values) < 2:
                _state["error"] = "Sheet has no data rows (check tab name)"
                log.warning("MasterSheet returned no rows")
                return
            headers = [str(h).strip() for h in values[0]]
            records = []
            for row in values[1:]:
                rec = {}
                for i, h in enumerate(headers):
                    if not h:
                        continue  # skip blank-header columns (the cause of the dup error)
                    rec[h] = row[i] if i < len(row) else ""
                records.append(rec)
            # Exact header names from Salem's master sheet take priority; substrings are a
            # fallback so the source keeps working if the sheet schema changes.
            cols = {
                "ch": self._pick(
                    headers,
                    exact=["ch_company_number", "company_number", "company number",
                           "companies_house_number"],
                    contains=["company_number", "company number", "companies house",
                              "crn", "ch_number", "ch number", "reg number", "registration"]),
                "name": self._pick(
                    headers,
                    exact=["company_name", "company name", "organisation_name",
                           "organization_name", "trading_name"],
                    contains=["company name", "company_name", "organisation",
                              "organization", "trading name"])
                or self._pick(headers, contains=["name"]),
                "emp": self._pick(
                    headers,
                    exact=["number of employees", "employees", "employee_count",
                           "num_employees"],
                    contains=["employee", "headcount", "staff", "team size"]),
                "rev": self._pick(
                    headers,
                    exact=["annual_turnover", "turnover", "annual_revenue", "revenue"],
                    contains=["turnover", "revenue"]),
                "sic": self._pick(headers, exact=["sic_code", "sic"], contains=["sic"]),
            }
            _state["headers"] = headers
            _state["error"] = None
            by_ch, by_name = {}, {}
            for r in records:
                if cols["ch"]:
                    k = _norm_ch(str(r.get(cols["ch"], "")))
                    if k:
                        by_ch.setdefault(k, r)
                if cols["name"]:
                    k = _norm_name(str(r.get(cols["name"], "")))
                    if k:
                        by_name.setdefault(k, r)
            _state.update({"loaded_at": time.time(), "by_ch": by_ch, "by_name": by_name,
                           "cols": cols, "n": len(records)})
            log.info("MasterSheet loaded %d rows; matched columns: %s", len(records), cols)

    def lookup(self, ch_number: str | None = None, name: str | None = None) -> dict | None:
        if not self.configured:
            return None
        self._load()
        if not _state["n"]:
            return None
        row = None
        if ch_number:
            row = _state["by_ch"].get(_norm_ch(ch_number))
        if not row and name:
            row = _state["by_name"].get(_norm_name(name))
        if not row:
            return None
        cols = _state["cols"]

        def g(key):
            col = cols.get(key)
            v = row.get(col) if col else None
            return v if v not in ("", None) else None

        used = {c for c in cols.values() if c}
        extra = {k: v for k, v in row.items() if k not in used and v not in ("", None)}
        return {"employees": g("emp"), "revenue": g("rev"), "sic": g("sic"),
                "extra": extra, "source": "mastersheet"}


mastersheet = MasterSheet()
