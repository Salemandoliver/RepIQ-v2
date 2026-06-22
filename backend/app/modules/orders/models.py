"""Order Entry data model (brief §14) — RepIQ's like-for-like replacement of the NetSuite Sales
Order module + the SharePoint Excel trackers.

Boring, normalised, auditable. One row per Sales Order (``Order``), one row per line item
(``OrderLine`` — the unit of commission), immutable status history (``OrderStatusLog``), multi-agent
splits (``OrderAgent``), disputes (``OrderDispute``), a BT-classified product catalogue
(``OrderProduct``), targets, the commission engine (pay plans → runs → statements → per-line
commissions) and Schedule 5 reconciliation. Every order is stamped with its BT financial month so
reporting lines up with the sales calendar.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...core.mixins import DomainBase
from ...db import Base

# ---- Order status state machine (brief §14.3) + badges (§14.2.2) ----
ORDER_STATUS = {
    "O": "With BT",
    "I": "Completed and Closed: To Be Billed",
    "J": "Completed and Closed: Fully Billed",
    "K": "Partially Paid",
    "L": "Paid in Full",
    "M": "Cancelled",
    "N": "Non-commissionable",
    "P": "Issues with Payment",
}
STATUS_BADGE = {
    "O": "WITH BT", "I": "PENDING BILLING", "J": "FULLY BILLED", "K": "PARTIALLY PAID",
    "L": "PAID", "M": "CANCELLED", "N": "NON-COMMISSIONABLE", "P": "PAYMENT ISSUE",
}
# Statuses that are "open" (commission still expected) vs terminal.
TERMINAL_STATUSES = {"L", "M", "N"}
CANCELLED_STATUSES = {"M"}
# LE acquisition status: a brand-new customer (acquisition) vs an existing customer who's bought
# from us before (in_life).
ACQUISITION_STATUS = ["acquisition", "in_life"]
SCHEDULE5_CHECK = ["on_correct", "on_incorrect", "not_on"]   # On S5 correct / incorrect / not on S5


class Customer(DomainBase, Base):
    """Customer LE — BT 'Legal Entity'. LE code + company name; linked to the wider Master DB later
    via ``external_ids``."""
    __tablename__ = "order_customers"
    le_code: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    company_name: Mapped[str] = mapped_column(String(255), index=True)
    external_ids: Mapped[dict] = mapped_column(JSON, default=dict)   # apollo/lemlist/jiminny/etc.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class OrderProduct(DomainBase, Base):
    """BT product catalogue, four-level hierarchy (brief §14.5): Class → Product Group 1 → Product
    Group 2 → Schedule 5 Area. Distinct from the campaigns/pillar catalogue."""
    __tablename__ = "order_products"
    name: Mapped[str] = mapped_column(String(200), index=True)
    product_class: Mapped[str | None] = mapped_column(String(80), nullable=True)
    product_group1: Mapped[str | None] = mapped_column(String(80), nullable=True)
    product_group2: Mapped[str | None] = mapped_column(String(80), nullable=True)
    schedule5_area: Mapped[str | None] = mapped_column(String(80), nullable=True)
    cobra: Mapped[str | None] = mapped_column(String(60), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Order(DomainBase, Base):
    """A Sales Order — the single most important record (brief §14.2)."""
    __tablename__ = "orders"

    order_number: Mapped[str] = mapped_column(String(20), unique=True, index=True)   # e.g. SO8358
    order_date: Mapped[date] = mapped_column(Date, index=True)
    financial_month: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)  # BT sales-month key
    # BT financial-year week (auto from order_date, but operator-editable). week_year = FY-start year.
    # Operations reconcile a week's orders against BT's Monday Schedule 5, so this is filterable.
    week_number: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    week_year: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)

    # "Order Placed" = it's been entered into the BT systems (like the Sales Tracker's Placed? flag).
    # An un-placed order may have missing details or be waiting on something before it can be placed.
    placed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    placed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    customer_id: Mapped[str | None] = mapped_column(ForeignKey("order_customers.id"), nullable=True)
    le_code: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    company_name: Mapped[str] = mapped_column(String(255), index=True, default="")
    le_acquisition_status: Mapped[str | None] = mapped_column(String(20), nullable=True)  # acquisition|renewal

    status: Mapped[str] = mapped_column(String(2), default="O", index=True)          # state machine code
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    main_order_number: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)  # BT ref
    opp_id: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)             # BT Opportunity ID
    vol_reference: Mapped[str | None] = mapped_column(String(60), nullable=True)
    admin_agent_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    has_been_rejected: Mapped[bool] = mapped_column(Boolean, default=False)
    order_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_notes_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    actual_order_closed_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    order_cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    cancellation_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cancellation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    bt_net_issue_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # CRQ tracking (brief §14.2.1)
    commission_crq_ref: Mapped[str | None] = mapped_column(String(60), nullable=True)
    commission_crq_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    commission_crq_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    reporting_crq_ref: Mapped[str | None] = mapped_column(String(60), nullable=True)
    reporting_crq_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reporting_crq_closed: Mapped[bool] = mapped_column(Boolean, default=False)

    exclude_from_ebp: Mapped[bool] = mapped_column(Boolean, default=False)
    delivery_terms: Mapped[str | None] = mapped_column(String(80), nullable=True)
    nature_of_transaction_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    country_of_origin: Mapped[str | None] = mapped_column(String(60), nullable=True)
    counterparty_vat: Mapped[str | None] = mapped_column(String(40), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="GBP")
    subsidiary: Mapped[str] = mapped_column(String(80), default="Synvestment Ltd")

    subtotal: Mapped[float] = mapped_column(Float, default=0.0)      # sum of line GM
    total: Mapped[float] = mapped_column(Float, default=0.0)         # = subtotal

    locked: Mapped[bool] = mapped_column(Boolean, default=False)     # set when its commission month is locked
    source: Mapped[str] = mapped_column(String(12), default="manual")   # manual | import
    import_batch: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    lines: Mapped[list["OrderLine"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    agents: Mapped[list["OrderAgent"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderLine(DomainBase, Base):
    """A line item (product) on an order — the unit of commission (brief §14.4)."""
    __tablename__ = "order_lines"
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    line_no: Mapped[int] = mapped_column(Integer, default=1)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("order_products.id"), nullable=True)
    item_name: Mapped[str] = mapped_column(String(200), default="")
    contract_value: Mapped[float] = mapped_column(Float, default=0.0)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    new_ren: Mapped[str | None] = mapped_column(String(12), nullable=True)            # new | renewal
    schedule5_area: Mapped[str | None] = mapped_column(String(80), nullable=True)
    product_group1: Mapped[str | None] = mapped_column(String(80), nullable=True)
    product_group2: Mapped[str | None] = mapped_column(String(80), nullable=True)
    cobra: Mapped[str | None] = mapped_column(String(60), nullable=True)
    gm: Mapped[float] = mapped_column(Float, default=0.0)                              # gross margin (commissionable)
    job_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    primary_split_pct: Mapped[float] = mapped_column(Float, default=100.0)
    second_split_pct: Mapped[float] = mapped_column(Float, default=0.0)
    date_closed: Mapped[date | None] = mapped_column(Date, nullable=True)
    bt_commission_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    schedule5_check: Mapped[str | None] = mapped_column(String(16), nullable=True)
    date_checked: Mapped[date | None] = mapped_column(Date, nullable=True)
    country_of_origin: Mapped[str | None] = mapped_column(String(60), nullable=True)

    order: Mapped[Order] = relationship(back_populates="lines")


class OrderStatusLog(DomainBase, Base):
    """Immutable record of every order status transition (brief §14.3)."""
    __tablename__ = "order_status_log"
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(2), nullable=True)
    to_status: Mapped[str] = mapped_column(String(2))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class OrderAgent(DomainBase, Base):
    """Sales-team allocation per order — who gets what share of commission (brief §14.6)."""
    __tablename__ = "order_agents"
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    agent_name: Mapped[str] = mapped_column(String(160), default="")   # cached / external name
    sales_role: Mapped[str | None] = mapped_column(String(30), nullable=True)  # first_sales_rep|second_sales_rep|closer|admin_agent|agent
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    split_pct: Mapped[float] = mapped_column(Float, default=0.0)
    contribution_pct: Mapped[float] = mapped_column(Float, default=0.0)
    contribution_amount: Mapped[float] = mapped_column(Float, default=0.0)

    order: Mapped[Order] = relationship(back_populates="agents")


class OrderDispute(DomainBase, Base):
    """Dispute raised by a customer/BT/internally on an order; may link to a CallIQ recording for
    evidence (brief §6.2)."""
    __tablename__ = "order_disputes"
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    dispute_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open")    # open | investigating | resolved
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    call_id: Mapped[int | None] = mapped_column(Integer, nullable=True)   # CallIQ call for dispute evidence
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class OrderTarget(DomainBase, Base):
    """Monthly revenue + volume target per rep (replaces the Sales Tracker target sheet)."""
    __tablename__ = "order_targets"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    financial_month: Mapped[date] = mapped_column(Date, index=True)
    revenue_target: Mapped[float] = mapped_column(Float, default=0.0)
    volume_target: Mapped[float] = mapped_column(Float, default=0.0)


# ---- Commission engine (brief §14.9c) ----
class PayPlan(DomainBase, Base):
    """Versioned commission rate configuration. Historical runs always use the plan that was active
    at the time (effective_date)."""
    __tablename__ = "pay_plans"
    name: Mapped[str] = mapped_column(String(120))
    effective_date: Mapped[date] = mapped_column(Date, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # config: {rates:[{match:{class?,group1?,group2?,schedule5?}, rate_pct}], default_rate_pct,
    #          min_order_gm, accelerators:[{from_pct,multiplier}], exclude_non_commissionable:true}
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class CommissionRun(DomainBase, Base):
    """A monthly commission statement run for a financial month (brief §14.9c)."""
    __tablename__ = "commission_runs"
    financial_month: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(14), default="draft")   # draft|calculated|approved|locked
    pay_plan_id: Mapped[str | None] = mapped_column(ForeignKey("pay_plans.id"), nullable=True)
    totals: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CommissionStatement(DomainBase, Base):
    """Per-rep statement within a commission run."""
    __tablename__ = "commission_statements"
    run_id: Mapped[str] = mapped_column(ForeignKey("commission_runs.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    rep_name: Mapped[str] = mapped_column(String(160), default="")
    gross_commission: Mapped[float] = mapped_column(Float, default=0.0)
    net_commission: Mapped[float] = mapped_column(Float, default=0.0)
    order_count: Mapped[int] = mapped_column(Integer, default=0)
    lines: Mapped[list] = mapped_column(JSON, default=list)            # per-line breakdown
    status: Mapped[str] = mapped_column(String(14), default="draft")  # draft|reviewed|disputed|approved
    flag_note: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---- Schedule 5 reconciliation (brief §14.9b) ----
class Schedule5Import(DomainBase, Base):
    __tablename__ = "schedule5_imports"
    filename: Mapped[str] = mapped_column(String(255), default="")
    financial_year: Mapped[str | None] = mapped_column(String(8), nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    signed_off: Mapped[bool] = mapped_column(Boolean, default=False)
    signed_off_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    signed_off_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Schedule5Row(DomainBase, Base):
    __tablename__ = "schedule5_rows"
    import_id: Mapped[str] = mapped_column(ForeignKey("schedule5_imports.id"), index=True)
    sales_rep: Mapped[str | None] = mapped_column(String(160), nullable=True)
    row_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    product: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contract_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    order_reference: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)
    schedule5_area: Mapped[str | None] = mapped_column(String(80), nullable=True)
    commission_status: Mapped[str | None] = mapped_column(String(60), nullable=True)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)


class Schedule5Reconciliation(DomainBase, Base):
    __tablename__ = "schedule5_reconciliation"
    import_id: Mapped[str] = mapped_column(ForeignKey("schedule5_imports.id"), index=True)
    row_id: Mapped[str | None] = mapped_column(ForeignKey("schedule5_rows.id"), nullable=True)
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), index=True)   # matched|mismatch|bt_only|repiq_only
    discrepancy: Mapped[dict] = mapped_column(JSON, default=dict)


class Schedule5Resolution(DomainBase, Base):
    __tablename__ = "schedule5_resolutions"
    reconciliation_id: Mapped[str] = mapped_column(ForeignKey("schedule5_reconciliation.id"), index=True)
    action: Mapped[str] = mapped_column(String(40))   # corrected_in_repiq|queried_with_bt|raised_crq|accepted_non_comm
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
