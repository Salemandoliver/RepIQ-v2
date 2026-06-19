"""HR module — Phase 1 data model (brief §5).

Core identity record (``Employee``, 1:1 with a login ``User``) plus the first domain tables:
personal details (including **preferred name / "known as"** and **profile photo**), contact
details, and emergency contacts. Role / contract / pay and the remaining domains follow in
later increments.

Tables are prefixed ``hr_`` and live in the default schema during the create_all→Alembic
transition; they move into a dedicated ``hr`` schema when Alembic is armed.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...core.mixins import DomainBase
from ...db import Base


class Employee(DomainBase, Base):
    __tablename__ = "hr_employees"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    employee_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")     # active | leaver | suspended
    reports_to_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("hr_employees.id"), nullable=True)

    user = relationship("User", lazy="joined", foreign_keys=[user_id])
    personal = relationship("EmployeePersonal", uselist=False, back_populates="employee",
                            cascade="all, delete-orphan")
    contact = relationship("EmployeeContact", uselist=False, back_populates="employee",
                           cascade="all, delete-orphan")
    emergency_contacts = relationship("EmployeeEmergencyContact", back_populates="employee",
                                      cascade="all, delete-orphan",
                                      order_by="EmployeeEmergencyContact.priority")
    role = relationship("EmployeeRole", uselist=False, back_populates="employee",
                        cascade="all, delete-orphan")
    employment = relationship("EmployeeContract", uselist=False, back_populates="employee",
                              cascade="all, delete-orphan")
    holiday = relationship("EmployeeHoliday", uselist=False, back_populates="employee",
                           cascade="all, delete-orphan")
    leave_records = relationship("LeaveRecord", back_populates="employee",
                                 cascade="all, delete-orphan", order_by="LeaveRecord.leave_date")


class EmployeePersonal(DomainBase, Base):
    __tablename__ = "hr_employee_personal"

    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hr_employees.id"), unique=True, index=True)
    # Self-controlled identity (brief §5.1)
    preferred_name: Mapped[str | None] = mapped_column(String(120), nullable=True)   # "known as"
    profile_photo: Mapped[str | None] = mapped_column(Text, nullable=True)           # data URL (→ R2 later)
    title: Mapped[str | None] = mapped_column(String(20), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    middle_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    dob: Mapped[date | None] = mapped_column(Date, nullable=True)
    sex: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gender_identity: Mapped[str | None] = mapped_column(String(60), nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(60), nullable=True)
    about: Mapped[str | None] = mapped_column(Text, nullable=True)
    ni_number: Mapped[str | None] = mapped_column(String(20), nullable=True)          # admin-only group

    employee = relationship("Employee", back_populates="personal")


class EmployeeContact(DomainBase, Base):
    __tablename__ = "hr_employee_contact"

    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hr_employees.id"), unique=True, index=True)
    work_email: Mapped[str | None] = mapped_column(String(255), nullable=True)        # admin-assigned
    work_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    personal_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    personal_mobile: Mapped[str | None] = mapped_column(String(40), nullable=True)
    addr_line1: Mapped[str | None] = mapped_column(String(160), nullable=True)
    addr_line2: Mapped[str | None] = mapped_column(String(160), nullable=True)
    town: Mapped[str | None] = mapped_column(String(80), nullable=True)
    county: Mapped[str | None] = mapped_column(String(80), nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    country: Mapped[str | None] = mapped_column(String(60), nullable=True)
    preferred_contact_method: Mapped[str | None] = mapped_column(String(40), nullable=True)

    employee = relationship("Employee", back_populates="contact")


class EmployeeRole(DomainBase, Base):
    """Current position (brief §12 — Role tab). Job title lives on the login ``User`` (used app-wide)
    and the line manager on ``Employee.reports_to_id``; this row holds the rest."""
    __tablename__ = "hr_employee_role"

    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hr_employees.id"), unique=True, index=True)
    department: Mapped[str | None] = mapped_column(String(120), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(60), nullable=True)              # band / level
    role_effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)     # current role since

    employee = relationship("Employee", back_populates="role")


class EmployeeContract(DomainBase, Base):
    """Employment contract (brief §12 — Contract tab). Pay/bank are a separate financial-scope
    domain and are not modelled here."""
    __tablename__ = "hr_employee_contract"

    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hr_employees.id"), unique=True, index=True)
    contract_type: Mapped[str | None] = mapped_column(String(40), nullable=True)      # Permanent / Fixed-term / Contractor
    working_pattern: Mapped[str | None] = mapped_column(String(40), nullable=True)    # Full-time / Part-time
    weekly_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    fte: Mapped[float | None] = mapped_column(Float, nullable=True)                   # 0.0–1.0
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    continuous_service_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    probation_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notice_period: Mapped[str | None] = mapped_column(String(40), nullable=True)
    work_location: Mapped[str | None] = mapped_column(String(80), nullable=True)      # Office / Hybrid / Remote / site

    employee = relationship("Employee", back_populates="employment")


class EmployeeHoliday(DomainBase, Base):
    """Holiday entitlement (brief §12 — Holiday tab). Days taken come from LeaveRecord rows
    (imported from the Holiday Tracker); the leave year is April–March."""
    __tablename__ = "hr_employee_holiday"

    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hr_employees.id"), unique=True, index=True)
    allowance_days: Mapped[float | None] = mapped_column(Float, nullable=True)        # annual entitlement
    carried_over_days: Mapped[float | None] = mapped_column(Float, default=0.0)       # from prior year
    includes_bank_holidays: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    employee = relationship("Employee", back_populates="holiday")


class LeaveRecord(DomainBase, Base):
    """A single day (or half-day) of absence (brief §12 — Holiday / Sick & absence).
    Imported from the Holiday Tracker; ``source`` records provenance for idempotent re-sync."""
    __tablename__ = "hr_leave_records"

    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hr_employees.id"), index=True)
    leave_date: Mapped[date] = mapped_column(Date, index=True)
    portion: Mapped[float] = mapped_column(Float, default=1.0)                         # 1.0 full / 0.5 half
    leave_type: Mapped[str] = mapped_column(String(40), default="Holiday")            # Holiday/Sick/Compassionate/Unpaid/Custom
    code: Mapped[str | None] = mapped_column(String(10), nullable=True)               # raw tracker code
    source: Mapped[str] = mapped_column(String(20), default="tracker")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    employee = relationship("Employee", back_populates="leave_records")


class EmployeeEmergencyContact(DomainBase, Base):
    __tablename__ = "hr_employee_emergency_contacts"

    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hr_employees.id"), index=True)
    full_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    relation: Mapped[str | None] = mapped_column(String(60), nullable=True)           # relationship to employee
    phone_primary: Mapped[str | None] = mapped_column(String(40), nullable=True)
    phone_secondary: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=1)                          # 1 = contact first
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    employee = relationship("Employee", back_populates="emergency_contacts")
