from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, Money


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


TEXT_FIELDS = [
    "supplier_name",
    "supplier_address",
    "supplier_tax_id",
    "customer_name",
    "customer_address",
    "customer_tax_id",
    "invoice_number",
    "po_number",
    "currency",
    "payment_terms",
    "notes",
]
DATE_FIELDS = ["invoice_date", "due_date"]
MONEY_FIELDS = ["subtotal", "discount", "tax_amount", "shipping", "total_amount", "amount_paid", "balance_due"]
ALL_FIELDS = TEXT_FIELDS + DATE_FIELDS + MONEY_FIELDS


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(200))
    reference: Mapped[str | None] = mapped_column(String(100))  # e.g. Fiverr order number
    client_note: Mapped[str | None] = mapped_column(Text)
    use_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_consent_provider: Mapped[str | None] = mapped_column(String(30))
    ai_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_job_sha", "job_id", "sha256"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    original_name: Mapped[str] = mapped_column(String(300))
    stored_name: Mapped[str | None] = mapped_column(String(64))  # internal random id, never the client's name
    sha256: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    pages: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    error: Mapped[str | None] = mapped_column(String(300))
    method: Mapped[str | None] = mapped_column(String(30))
    duplicate_of: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), unique=True)
    supplier_name: Mapped[str | None] = mapped_column(String(300))
    supplier_address: Mapped[str | None] = mapped_column(Text)
    supplier_tax_id: Mapped[str | None] = mapped_column(String(60))
    customer_name: Mapped[str | None] = mapped_column(String(300))
    customer_address: Mapped[str | None] = mapped_column(Text)
    customer_tax_id: Mapped[str | None] = mapped_column(String(60))
    invoice_number: Mapped[str | None] = mapped_column(String(100))
    po_number: Mapped[str | None] = mapped_column(String(100))
    currency: Mapped[str | None] = mapped_column(String(3))
    payment_terms: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    invoice_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    subtotal: Mapped[Decimal | None] = mapped_column(Money)
    discount: Mapped[Decimal | None] = mapped_column(Money)
    tax_amount: Mapped[Decimal | None] = mapped_column(Money)
    shipping: Mapped[Decimal | None] = mapped_column(Money)
    total_amount: Mapped[Decimal | None] = mapped_column(Money)
    amount_paid: Mapped[Decimal | None] = mapped_column(Money)
    balance_due: Mapped[Decimal | None] = mapped_column(Money)
    source_page: Mapped[int | None] = mapped_column(Integer)
    extraction_method: Mapped[str | None] = mapped_column(String(30))
    original: Mapped[dict] = mapped_column(JSON, default=dict)  # extracted values as strings, never modified
    meta: Mapped[dict] = mapped_column(JSON, default=dict)  # per-field confidence/source/evidence
    issues: Mapped[list] = mapped_column(JSON, default=list)
    ai: Mapped[dict | None] = mapped_column(JSON)
    edited_fields: Mapped[list] = mapped_column(JSON, default=list)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LineItem(Base):
    __tablename__ = "line_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    quantity: Mapped[Decimal | None] = mapped_column(Money)
    unit: Mapped[str | None] = mapped_column(String(30))
    unit_price: Mapped[Decimal | None] = mapped_column(Money)
    discount: Mapped[Decimal | None] = mapped_column(Money)
    tax_rate: Mapped[Decimal | None] = mapped_column(Money)
    tax_amount: Mapped[Decimal | None] = mapped_column(Money)
    line_total: Mapped[Decimal | None] = mapped_column(Money)
    reliable: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(String(300))
    page: Mapped[int | None] = mapped_column(Integer)


class Correction(Base):
    __tablename__ = "corrections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    field: Mapped[str] = mapped_column(String(50))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DuplicateCandidate(Base):
    __tablename__ = "duplicate_candidates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    doc_a: Mapped[str] = mapped_column(String(32))
    doc_b: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(20))
    score: Mapped[float] = mapped_column(Float)


class ExportFile(Base):
    __tablename__ = "export_files"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    filename: Mapped[str] = mapped_column(String(200))
    stored_name: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
