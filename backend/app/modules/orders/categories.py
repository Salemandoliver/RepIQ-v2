"""BT targeting categories — Data / Cloud / Mobile (the three buckets BT targets BTLB on).

Every product sits under one of three top-level categories. BT's Schedule 5 area is the most reliable
signal (Connectivity → Data, Cloud and SOV → Cloud, Mobile and SOV → Mobile); we fall back to the
product group / area otherwise. 'Data' is the connectivity family — BT Net, Broadband, SOGEA, Ethernet,
SD-WAN, Security, VAS, Data Networks & Services, etc.
"""
from __future__ import annotations

DATA, CLOUD, MOBILE = "Data", "Cloud", "Mobile"
CATEGORIES = [DATA, CLOUD, MOBILE]


def bt_category(group1=None, group2=None, area=None, schedule5=None) -> str:
    """Resolve a product's BT targeting category from its classification fields."""
    s5 = (schedule5 or "").lower()
    if "mobile" in s5:
        return MOBILE
    if "cloud" in s5:
        return CLOUD
    if "connectivity" in s5:
        return DATA
    text = " ".join(str(x or "") for x in (group1, group2, area)).lower()
    if "mobile" in text:
        return MOBILE
    if "cloud" in text:
        return CLOUD
    return DATA


def line_category(line) -> str:
    return bt_category(line.product_group1, line.product_group2, line.schedule5_area, line.schedule5_area)


def order_breakdown(order) -> dict:
    """GM (SOV) per BT category for one order — for Data/Cloud/Mobile reporting and targets."""
    out = {DATA: 0.0, CLOUD: 0.0, MOBILE: 0.0}
    for ln in order.lines:
        if ln.deleted_at is not None:
            continue
        out[line_category(ln)] += (ln.gm or 0.0)
    return {k: round(v, 2) for k, v in out.items()}
