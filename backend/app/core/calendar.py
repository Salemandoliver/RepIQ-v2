"""Financial-month calendar — promoted to the platform core.

BT Local Business runs on a sales calendar where the month starts on the first Monday on or
before the 1st (brief §3 / Order Entry §14.10). This is the single definition used by SalesIQ,
the commission engine, HR reporting, and any future module — never the raw calendar month.

The implementation lives in ``services/salesiq/fincal.py`` today; this module re-exports it so
new code imports from ``app.core.calendar``. When the SalesIQ code is moved under ``modules/``
the implementation moves here and ``fincal.py`` becomes the shim.
"""
from __future__ import annotations

from ..services.salesiq.fincal import (  # noqa: F401
    MONTH_NAMES,
    MONTH_ABBR,
    sales_month_start,
    sales_month,
    current_sales_month,
    financial_quarter,
    quarter_months,
    fy_months,
    period_bounds,
    days_remaining,
    weekdays_between,
    to_dt,
)
