"""Product catalogue — the company's real products/pillars (Roadmap Phase 0).

A light reference table that Campaigns link to and the intelligence layer's entity graph uses
(attach-rate, product gaps, sov_multiplier). Admin-managed; seeded with the common BT products.
"""
from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...core.mixins import DomainBase
from ...db import Base

PILLARS = ["Connectivity", "Cloud", "Mobile", "Security", "Hardware", "Software", "Other"]


class Product(DomainBase, Base):
    __tablename__ = "catalog_products"

    name: Mapped[str] = mapped_column(String(120), index=True)
    pillar: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sku: Mapped[str | None] = mapped_column(String(60), nullable=True)
    keywords: Mapped[str | None] = mapped_column(Text, nullable=True)   # comma list — detection hints
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


# Seed set — the products RepIQ should know about out of the box.
_SEED = [
    ("BTnet (leased line)", "Connectivity", "btnet, leased line, dedicated internet, ethernet"),
    ("Broadband / FTTP", "Connectivity", "broadband, fttp, fibre, full fibre, fttc"),
    ("Cloud Voice / Phone", "Cloud", "cloud voice, cloud phone, voip, hosted voice"),
    ("Cloud Security", "Security", "cloud security, web protect, endpoint, antivirus, firewall"),
    ("Mobile / SIM", "Mobile", "mobile, sim, airtime, data sim"),
    ("Microsoft 365", "Software", "microsoft 365, m365, office 365, teams licences"),
    ("iPhone (handsets)", "Hardware", "iphone, handset, device"),
    ("Wi-Fi / Networking", "Connectivity", "wifi, wi-fi, access point, networking, switch"),
]


def seed_products(db) -> None:
    """Idempotent: seed the common products if the catalogue is empty."""
    if db.query(Product.id).first() is not None:
        return
    for i, (name, pillar, kw) in enumerate(_SEED):
        db.add(Product(name=name, pillar=pillar, keywords=kw, sort_order=(i + 1) * 10, active=True))
    db.commit()
