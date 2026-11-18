"""Decimal-safe validation of a parsed invoice. Returns issue dicts {code, severity, message, field}."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from .parser import CENT, ParsedInvoice

REQUIRED = ["supplier_name", "invoice_number", "invoice_date", "currency", "total_amount"]


def _issue(code, severity, message, field=None):
    return {"code": code, "severity": severity, "message": message, "field": field}


def validate(inv: ParsedInvoice, today: date | None = None) -> list[dict]:
    today = today or date.today()
    out: list[dict] = []
    g = inv.get
    for f in REQUIRED:
        if g(f) in (None, ""):
            out.append(_issue("missing_field", "warning", f"Missing {f.replace('_', ' ')}", f))
    sub, tax, tot = g("subtotal"), g("tax_amount"), g("total_amount")
    disc = g("discount") or Decimal(0)
    ship = g("shipping") or Decimal(0)
    if sub is not None and tot is not None:
        expected = sub - disc + ship + (tax if tax is not None else Decimal(0))
        if abs(expected - tot) > CENT:
            if tax is None:
                out.append(
                    _issue("total_mismatch", "warning", f"Subtotal {sub} does not equal total {tot} and no tax found", "total_amount")
                )
            else:
                out.append(
                    _issue(
                        "total_mismatch", "error", f"Subtotal - discount + shipping + tax = {expected} but total is {tot}", "total_amount"
                    )
                )
    elif tot is not None and sub is None:
        out.append(_issue("no_subtotal", "info", "No subtotal found; total could not be cross-checked", "subtotal"))
    if g("amount_paid") is not None and g("balance_due") is not None and tot is not None:
        if abs(tot - g("amount_paid") - g("balance_due")) > CENT:
            out.append(_issue("balance_mismatch", "warning", "total - paid does not equal balance due", "balance_due"))
    inv_d, due_d = g("invoice_date"), g("due_date")
    if inv_d and inv_d > today:
        out.append(_issue("future_date", "warning", "Invoice date is in the future", "invoice_date"))
    if inv_d and due_d and due_d < inv_d:
        out.append(_issue("due_before_invoice", "warning", "Due date is before invoice date", "due_date"))
    if tot is not None and tot < 0:
        out.append(_issue("negative_total", "info", "Total is negative (credit note?)", "total_amount"))
    for it in inv.line_items:
        if not it.reliable:
            out.append(_issue("line_item_unreliable", "warning", f"Line item '{it.description[:40]}': {it.note}", "line_items"))
    if inv.line_items and sub is not None:
        s = sum((i.line_total or Decimal(0) for i in inv.line_items), Decimal(0))
        if abs(s - sub) > CENT:
            out.append(_issue("lines_vs_subtotal", "warning", f"Line items sum to {s}, subtotal is {sub}", "subtotal"))
    for w in inv.warnings:
        if "ambiguous" in w.lower():
            out.append(_issue("ambiguous_date", "warning", w, "invoice_date"))
    return out
