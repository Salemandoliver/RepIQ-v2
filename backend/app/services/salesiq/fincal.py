"""BT Local Business financial calendar (Brief §6.8).

Rules:
  - Sales month starts on the first Monday on or before the 1st of the calendar month
    (e.g. 1 May 2026 is a Friday -> May sales month starts Mon 27 April).
  - Quarters: Q1 Apr-Jun, Q2 Jul-Sep, Q3 Oct-Dec, Q4 Jan-Mar.
  - Financial year label: FY27 = April 2026 - March 2027.
  - All MTD/QTD/YTD windows use these boundaries, never the calendar month.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

MONTH_NAMES = ["", "January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]
MONTH_ABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
              "Oct", "Nov", "Dec"]


def sales_month_start(year: int, cal_month: int) -> date:
    """First Monday on or before the 1st of the given calendar month."""
    first = date(year, cal_month, 1)
    return first - timedelta(days=first.weekday())   # weekday(): Mon=0 .. Sun=6


def _add_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _sub_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def sales_month(year: int, month: int) -> dict:
    """The sales month for a calendar (year, month) -> {year, month, start, end, label}."""
    start = sales_month_start(year, month)
    ny, nm = _add_month(year, month)
    end = sales_month_start(ny, nm) - timedelta(days=1)
    return {"year": year, "month": month, "start": start, "end": end,
            "label": f"{MONTH_NAMES[month]} {year}"}


def current_sales_month(d: date | None = None) -> dict:
    """The sales month containing date d."""
    d = d or date.today()
    start = sales_month_start(d.year, d.month)
    year, month = d.year, d.month
    if d < start:                                    # belongs to previous sales month
        year, month = _sub_month(d.year, d.month)
    else:
        ny, nm = _add_month(d.year, d.month)
        if d >= sales_month_start(ny, nm):           # belongs to next sales month
            year, month = ny, nm
    return sales_month(year, month)


def financial_quarter(d: date | None = None) -> dict:
    """{q, fyLabel, label} for the financial quarter containing d."""
    d = d or date.today()
    m = d.month
    if 4 <= m <= 6:
        q = 1
    elif 7 <= m <= 9:
        q = 2
    elif 10 <= m <= 12:
        q = 3
    else:
        q = 4
    fy_end_year = d.year + 1 if m >= 4 else d.year
    fy = f"FY{fy_end_year % 100:02d}"
    return {"q": q, "fyLabel": fy, "label": f"Q{q} {fy}"}


_QUARTER_MONTHS = {1: [4, 5, 6], 2: [7, 8, 9], 3: [10, 11, 12], 4: [1, 2, 3]}


def quarter_months(d: date | None = None) -> list[tuple[int, int]]:
    """(year, month) pairs for the quarter up to & including the current sales month."""
    d = d or date.today()
    cur = current_sales_month(d)
    q = financial_quarter(d)["q"]
    out = []
    for m in _QUARTER_MONTHS[q]:
        # Q4 (Jan-Mar) falls in the next calendar year relative to the FY start
        yr = cur["year"] if not (q == 4) else cur["year"]
        out.append((yr, m))
        if (yr, m) == (cur["year"], cur["month"]):
            break
    return out


def fy_months(d: date | None = None) -> list[tuple[int, int]]:
    """(year, month) pairs from the start of the financial year up to the current month."""
    d = d or date.today()
    cur = current_sales_month(d)
    # FY starts in April. Determine the April year for this FY.
    fy_start_year = cur["year"] if cur["month"] >= 4 else cur["year"] - 1
    out, y, m = [], fy_start_year, 4
    while True:
        out.append((y, m))
        if (y, m) == (cur["year"], cur["month"]):
            break
        y, m = _add_month(y, m)
        if len(out) > 12:
            break
    return out


def period_bounds(d: date | None = None, period: str = "mtd") -> dict:
    """Start/end dates + a human label for a dashboard period."""
    d = d or date.today()
    cur = current_sales_month(d)
    if period == "daily":
        return {"start": d, "end": d, "label": d.strftime("%d %b %Y")}
    if period == "weekly":
        wk = (d - cur["start"]).days // 7
        wstart = cur["start"] + timedelta(days=wk * 7)
        return {"start": wstart, "end": min(wstart + timedelta(days=6), cur["end"]),
                "label": f"Week {wk + 1} · {cur['label']}"}
    if period == "qtd":
        fq = financial_quarter(d)
        first_year, first_month = quarter_months(d)[0]
        return {"start": sales_month_start(first_year, first_month), "end": cur["end"],
                "label": f"{fq['label']} (QTD)"}
    if period == "ytd":
        first_year, first_month = fy_months(d)[0]
        return {"start": sales_month_start(first_year, first_month), "end": cur["end"],
                "label": f"{financial_quarter(d)['fyLabel']} (YTD)"}
    # default: mtd
    return {"start": cur["start"], "end": cur["end"], "label": f"{cur['label']} (MTD)"}


def days_remaining(d: date | None = None) -> int:
    d = d or date.today()
    return max(0, (current_sales_month(d)["end"] - d).days)


def weekdays_between(start: date, end: date) -> int:
    """Mon-Fri count in [start, end] inclusive (for daily-target × working-days)."""
    if end < start:
        return 0
    days = (end - start).days + 1
    full_weeks, extra = divmod(days, 7)
    count = full_weeks * 5
    for i in range(extra):
        if (start + timedelta(days=full_weeks * 7 + i)).weekday() < 5:
            count += 1
    return count


def to_dt(d: date) -> datetime:
    return datetime(d.year, d.month, d.day)
