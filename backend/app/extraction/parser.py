"""Deterministic invoice field + line-item parser (EN/DE/FR/ES labels).

Rules: missing stays None; tax == 0 is a real value (Decimal('0')), distinct from missing;
all money is Decimal; every field records evidence text and a confidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .numbers import AMOUNT_RE, DATE_TOKEN_RE, infer_decimal_separator, parse_amount, parse_date

CENT = Decimal("0.01")

LANG_HINTS = {
    "de": ["rechnung", "mwst", "ust", "gesamtbetrag", "zwischensumme", "menge", "fällig", "datum"],
    "fr": ["facture", "tva", "échéance", "sous-total", "quantité", "date de"],
    "es": ["factura", "iva", "vencimiento", "cantidad", "importe", "fecha"],
    "en": ["invoice", "subtotal", "total", "quantity", "due date", "bill to", "balance"],
}
CURRENCY_CODES = [
    "USD",
    "EUR",
    "GBP",
    "CHF",
    "CAD",
    "AUD",
    "JPY",
    "SEK",
    "NOK",
    "DKK",
    "PLN",
    "CZK",
    "INR",
    "MXN",
    "BRL",
    "ZAR",
    "NZD",
    "AED",
]
SYMBOLS = {"€": "EUR", "£": "GBP", "$": "USD", "¥": "JPY", "₹": "INR"}

DESC_LABELS = (
    "description",
    "beschreibung",
    "bezeichnung",
    "désignation",
    "designation",
    "descripción",
    "descripcion",
    "artikel",
    "article",
    "product",
    "produit",
    "producto",
    "item",
)
QTY_LABELS = ("quantity", "qty", "menge", "quantité", "quantite", "cantidad", "stk", "stück", "stuck", "ct")
UNIT_PRICE_LABELS = (
    "unit price",
    "unitprice",
    "einzelpreis",
    "prix unitaire",
    "precio unitario",
    "precio unit.",
    "prix unit.",
    "price",
    "preis",
    "prix",
    "precio",
    "rate",
    "tarif",
    "p.u.",
)
DISCOUNT_LABELS = ("discount", "rabatt", "remise", "descuento")
TAX_RATE_LABELS = ("sales tax", "tax rate", "vat", "mwst.", "mwst", "tva", "iva", "ust", "gst", "tax")
AMOUNT_LABELS = ("line total", "line amount", "amount", "total", "betrag", "gesamt", "montant", "importe", "sum", "value")

L = {
    "subtotal": r"sub\s*-?\s*total|zwischensumme|nettobetrag|summe netto|sous-total|total ht|base imponible|subtotal",
    "discount": r"discount|rabatt|remise|descuento",
    "tax": r"sales tax|vat|tax|mwst\.?|mehrwertsteuer|umsatzsteuer|ust\.?|tva|iva|impuesto",
    "shipping": r"shipping|freight|delivery|versand|porto|frais de port|livraison|envío|envio",
    "total": r"grand total|invoice total|total amount|gesamtbetrag|gesamtsumme|rechnungsbetrag|bruttobetrag|total ttc|importe total|total",
    "paid": r"amount paid|paid|bereits gezahlt|anzahlung|déjà payé|pagado",
    "balance": r"balance due|amount due|total due|zu zahlen|restbetrag|net à payer|solde|saldo|importe pendiente",
}
TOTAL_EXCLUDE = re.compile(r"sub\s*-?\s*total|zwischensumme|sous-total|total ht|due|zu zahlen|net à payer|tax|vat|mwst|tva|iva", re.I)


@dataclass
class FieldValue:
    value: Any
    evidence: str = ""
    confidence: float = 0.0
    page: int | None = None
    source: str = "rules"  # rules | ai:<provider>
    alternatives: list = field(default_factory=list)  # earlier values replaced by a better source


@dataclass
class LineItem:
    description: str
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    discount: Decimal | None = None
    tax_rate: Decimal | None = None
    tax_amount: Decimal | None = None
    line_total: Decimal | None = None
    reliable: bool = True
    note: str | None = None
    page: int | None = None


@dataclass
class ParsedInvoice:
    fields: dict[str, FieldValue] = field(default_factory=dict)
    line_items: list[LineItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    language: str = "en"
    decimal_sep: str | None = None
    dayfirst: bool | None = None

    def get(self, name: str) -> Any:
        fv = self.fields.get(name)
        return fv.value if fv else None


def detect_language(text: str) -> str:
    low = text.lower()
    scores = {k: sum(low.count(w) for w in ws) for k, ws in LANG_HINTS.items()}
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] else "en"


def detect_currency(text: str) -> FieldValue | None:
    counts: dict[str, int] = {}
    for code in CURRENCY_CODES:
        n = len(re.findall(rf"\b{code}\b", text))
        if n:
            counts[code] = counts.get(code, 0) + n * 2
    for sym, code in SYMBOLS.items():
        n = text.count(sym)
        if n:
            counts[code] = counts.get(code, 0) + n
    if re.search(r"\bEuro?s?\b", text):
        counts["EUR"] = counts.get("EUR", 0) + 1
    if not counts:
        return None
    best = max(counts, key=lambda k: counts[k])
    return FieldValue(best, f"currency evidence x{counts[best]}", 0.9 if len(counts) == 1 else 0.6)


def detect_region(text: str) -> str | None:
    if re.search(r"\bABN\b", text):
        return "AU"
    if re.search(r"\bBN\b", text):
        return "CA"
    if re.search(r"\bEIN\b", text) or re.search(r"\bSales\s+tax\b", text, re.I):
        return "US"
    if re.search(r"\bVAT\s*(?:ID|No\.?|Number)\b", text, re.I):
        return "GB"
    if re.search(r"USt-?IdNr\.?", text, re.I):
        return "DE"
    if re.search(r"N[°º]\s*TVA", text, re.I):
        return "FR"
    if re.search(r"\bNIF\b", text):
        return "ES"
    if re.search(r"\bUID\b", text):
        return "CH"
    return None


def _amounts_on_line(line: str, ds: str | None) -> list[Decimal]:
    out = []
    for m in AMOUNT_RE.finditer(line):
        tail = line[m.end() : m.end() + 2]
        if tail.strip().startswith("%"):
            continue
        v = parse_amount(m.group(0), ds)
        if v is not None:
            out.append(v)
    return out


def _labelled_amount(
    lines: list[tuple[int, str]], pattern: str, ds: str | None, exclude: re.Pattern | None = None, pick_last_line: bool = False
) -> FieldValue | None:
    rx = re.compile(rf"(?<![A-Za-zäöüéèà])(?:{pattern})(?![A-Za-zäöüéèà])", re.I)
    hits = []
    for pg, ln in lines:
        m = rx.search(ln)
        if not m or (exclude and exclude.search(ln)):
            continue
        after = ln[m.end() :]
        amts = _amounts_on_line(after, ds)
        if amts:
            hits.append((pg, ln.strip(), amts[-1]))
    if not hits:
        return None
    pg, ln, v = hits[-1] if pick_last_line else hits[0]
    return FieldValue(v, ln, 0.85, pg)


def _labelled_date(lines, pattern: str, dayfirst: bool | None) -> tuple[FieldValue | None, bool]:
    rx = re.compile(rf"(?:{pattern})", re.I)
    for pg, ln in lines:
        m = rx.search(ln)
        if not m:
            continue
        tail = ln[m.end() :]
        dm = DATE_TOKEN_RE.search(tail)
        if not dm:
            continue
        d, amb = parse_date(dm.group(0), dayfirst)
        if d:
            return FieldValue(d, ln.strip(), 0.6 if amb else 0.9, pg), amb
    return None, False


def _split_lines(pages: list[str]) -> list[tuple[int, str]]:
    return [(i + 1, ln.rstrip()) for i, t in enumerate(pages) for ln in t.splitlines() if ln.strip()]


def _label_index(header: str, labels: tuple[str, ...]) -> int | None:
    low = header.lower()
    for label in sorted(labels, key=len, reverse=True):
        index = low.find(label.lower())
        if index >= 0:
            return index
    return None


def _column_layout(header: str) -> dict[str, int] | None:
    if ":" in header:
        return None
    raw: list[tuple[str, int]] = []
    for key, labels in (
        ("description", DESC_LABELS),
        ("qty", QTY_LABELS),
        ("unit_price", UNIT_PRICE_LABELS),
        ("discount", DISCOUNT_LABELS),
        ("tax_rate", TAX_RATE_LABELS),
        ("amount", AMOUNT_LABELS),
    ):
        index = _label_index(header, labels)
        if index is not None:
            raw.append((key, index))
    keys = {key for key, _ in raw}
    if "description" not in keys or "amount" not in keys:
        return None
    return dict(raw)


def parse_invoice(pages: list[str]) -> ParsedInvoice:
    full = "\n".join(pages)
    inv = ParsedInvoice()
    inv.language = detect_language(full)
    inv.decimal_sep = infer_decimal_separator(full)
    ds = inv.decimal_sep
    lines = _split_lines(pages)

    # dates: infer day-first from unambiguous numeric dates, else from language
    num_dates = re.findall(r"\b(\d{1,2})[./-](\d{1,2})[./-]\d{2,4}\b", full)
    region = detect_region(full)
    if any(int(a) > 12 for a, _ in num_dates):
        inv.dayfirst = True
    elif any(int(b) > 12 for _, b in num_dates):
        inv.dayfirst = False
    elif region == "US":
        inv.dayfirst = False
    elif region in ("GB", "AU", "CA", "DE", "FR", "ES", "CH"):
        inv.dayfirst = True
    elif "." in "".join(re.findall(r"\b\d{1,2}([./-])\d{1,2}[./-]\d{2,4}\b", full)) or inv.language in ("de", "fr", "es"):
        inv.dayfirst = True
    f = inv.fields
    ambiguous = False
    d, a1 = _labelled_date(
        lines,
        r"due date|payment due|due on|fällig(?:keit)?(?:sdatum)?|zahlbar bis|date d'échéance|échéance|vencimiento|fecha de vencimiento",
        inv.dayfirst,
    )
    if d:
        f["due_date"] = d
    d2, a2 = _labelled_date(
        lines, r"invoice date|date of issue|rechnungsdatum|date de facture|fecha de factura|fecha|datum|date", inv.dayfirst
    )
    if d2 and d and d2.evidence == d.evidence:  # same line caught both: re-run excluding due words
        d2 = None
        for pg, ln in lines:
            if re.search(r"due|fällig|échéance|vencimiento", ln, re.I):
                continue
            r, a2 = _labelled_date(
                [(pg, ln)], r"invoice date|rechnungsdatum|date de facture|fecha de factura|fecha|datum|date", inv.dayfirst
            )
            if r:
                d2 = r
                break
    if d2:
        f["invoice_date"] = d2
    ambiguous = (a1 and "due_date" in f) or (a2 and "invoice_date" in f)
    if ambiguous:
        inv.warnings.append("Numeric date is ambiguous (day/month order); verify manually.")

    # invoice number
    rx = re.compile(
        r"(?:invoice|inv\.?|rechnung(?:s)?|facture|factura)\s*(?:nummer|número|number|num\.?|no\.?|nr\.?|n°|#)?\s*[:#]?\s*([A-Z0-9][A-Z0-9\-/_.]{2,})",
        re.I,
    )
    for pg, ln in lines:
        if re.search(r"invoice date|rechnungsdatum|date de facture|invoice to", ln, re.I):
            continue
        m = rx.search(ln)
        if m and re.search(r"\d", m.group(1)) and not DATE_TOKEN_RE.fullmatch(m.group(1)):
            f["invoice_number"] = FieldValue(m.group(1).rstrip(".-"), ln.strip(), 0.85, pg)
            break
    # PO number
    m = re.search(
        r"(?:purchase order|p\.?o\.?|bestellnummer|bestell-?nr\.?|orden de compra|bon de commande)\s*(?:no\.?|number|#|nr\.?)?\s*[:#]?\s*([A-Z0-9][A-Z0-9\-/_]{2,})",
        full,
        re.I,
    )
    if m and re.search(r"\d", m.group(1)):
        f["po_number"] = FieldValue(m.group(1), m.group(0), 0.8)

    # currency
    c = detect_currency(full)
    if c:
        f["currency"] = c

    # money
    for name, key in [
        ("subtotal", "subtotal"),
        ("discount", "discount"),
        ("shipping", "shipping"),
        ("amount_paid", "paid"),
        ("balance_due", "balance"),
    ]:
        v = _labelled_amount(lines, L[key], ds)
        if v:
            f[name] = v
    tax_lines = [(p, l) for p, l in lines if not re.search(r"tax id|vat id|vat no|ust-?id|vat number|tax no", l, re.I)]
    v = _labelled_amount(tax_lines, L["tax"], ds)
    if v:
        f["tax_amount"] = v
    v = _labelled_amount(lines, L["total"], ds, exclude=TOTAL_EXCLUDE, pick_last_line=True)
    if v:
        f["total_amount"] = v
    if "tax_amount" not in f and "subtotal" in f and "total_amount" in f:
        derived = f["total_amount"].value - f["subtotal"].value
        if "shipping" in f:
            derived -= f["shipping"].value
        if "discount" in f:
            derived += f["discount"].value
        if derived >= 0:
            f["tax_amount"] = FieldValue(derived, "derived from subtotal and total", 0.5)
    m = re.search(
        r"(?:payment terms?|zahlungsbedingungen|zahlungsziel|conditions de paiement|condiciones de pago)\s*[:\-]?\s*(.+)", full, re.I
    )
    if m:
        f["payment_terms"] = FieldValue(m.group(1).strip()[:200], m.group(0)[:200], 0.8)
    m = re.search(r"(?:^|\n)\s*(?:notes?|bemerkung(?:en)?|remarques?|notas?)\s*[:\-]\s*(.+)", full, re.I)
    if m:
        f["notes"] = FieldValue(m.group(1).strip()[:500], m.group(0).strip()[:200], 0.7)

    # tax ids (first = supplier, second = customer)
    ids = re.findall(
        r"(?:VAT|USt-?IdNr\.?|Tax)\s*(?:ID|No\.?|Number|Nr\.?)?\s*[:#]?\s*([A-Z]{2}[ ]?[A-Z0-9]{8,12}|\d{2}-\d{7})|(?:EIN|TVA|NIF|CIF)\s*[:#]?\s*([A-Z0-9\-]{8,})",
        full,
        re.I,
    )
    flat = [a or b for a, b in ids if (a or b)]
    if flat:
        f["supplier_tax_id"] = FieldValue(flat[0], "tax id", 0.6)
    if len(flat) > 1:
        f["customer_tax_id"] = FieldValue(flat[1], "tax id", 0.5)

    # parties
    for pg, ln in lines[:8]:
        s = ln.strip()
        if len(s) > 2 and not re.search(r"invoice|rechnung|facture|factura|^\W*\d", s, re.I):
            f["supplier_name"] = FieldValue(s, s, 0.5, pg)
            break
    for i, (pg, ln) in enumerate(lines):
        if re.search(r"^\s*(?:bill to|invoice to|sold to|rechnung an|rechnungsempfänger|facturé à|facturar a|cliente)\s*:?\s*$", ln, re.I):
            blk = [l.strip() for _, l in lines[i + 1 : i + 4]]
            if blk:
                f["customer_name"] = FieldValue(blk[0], blk[0], 0.6, pg)
                if len(blk) > 1:
                    f["customer_address"] = FieldValue(", ".join(blk[1:3]), ", ".join(blk[1:3]), 0.4, pg)
            break
    if "supplier_name" in f:
        idx = next((i for i, (_, l) in enumerate(lines) if l.strip() == f["supplier_name"].value), None)
        if idx is not None:
            addr = [
                l.strip()
                for _, l in lines[idx + 1 : idx + 3]
                if re.search(r"\d", l) and not re.search(r"invoice|rechnung|vat|tax|date|datum", l, re.I)
            ]
            if addr:
                f["supplier_address"] = FieldValue(", ".join(addr), ", ".join(addr), 0.4)

    inv.line_items = parse_line_items(lines, ds, inv)
    return inv


def parse_line_items(lines: list[tuple[int, str]], ds: str | None, inv: ParsedInvoice) -> list[LineItem]:
    hdr = re.compile(
        r"(description|beschreibung|bezeichnung|désignation|designation|descripción|descripcion|artikel|article|product|produit|producto|item)"
        r".*(qty|quantity|menge|quantité|quantite|cantidad|price|preis|prix|precio|amount|betrag|gesamt|montant|importe)"
        r"|(qty|quantity|menge|quantité|quantite|cantidad).*(price|preis|prix|precio|amount|betrag|gesamt|montant|importe)",
        re.I,
    )
    end = re.compile(
        r"^\s*(?:sub\s*-?\s*total|zwischensumme|nettobetrag|summe netto|sous-total|total ht|base imponible|total|summe|gesamt)",
        re.I,
    )
    skip = re.compile(
        r"^\s*(?:tax|vat|mwst|tva|iva|sales tax|gst|shipping|versand|freight|delivery|frais de port|livraison|envío|envio|discount|rabatt|remise|descuento|amount due|balance due|amount paid|paid|zu zahlen)\b",
        re.I,
    )
    start: int | None = None
    layout: dict[str, int] | None = None
    for i, (_, ln) in enumerate(lines):
        if re.search(r"\d", ln):
            continue
        lay = _column_layout(ln)
        if lay:
            start, layout = i, lay
            break
        if hdr.search(ln):
            start, layout = i, None
            break
    if start is None:
        return []
    columns = sorted(layout.items(), key=lambda kv: kv[1]) if layout else []
    items: list[LineItem] = []
    for pg, ln in lines[start + 1 :]:
        if end.search(ln):
            break
        if skip.match(ln):
            continue
        matches: list[tuple[re.Match[str], Decimal]] = []
        for m in AMOUNT_RE.finditer(ln):
            if ln[m.end() : m.end() + 2].strip().startswith("%"):
                continue
            value = parse_amount(m.group(0), ds)
            if value is not None:
                matches.append((m, value))
        if not matches:
            continue
        assigned: dict[str, list[tuple[re.Match[str], Decimal]]] = {}
        for pair in matches:
            end_pos = pair[0].end()
            key = columns[0][0] if columns else None
            for name, col_start in columns:
                if end_pos >= col_start:
                    key = name
                else:
                    break
            if key:
                assigned.setdefault(key, []).append(pair)

        qty_pair = assigned["qty"][-1] if assigned.get("qty") else None
        unit_pair = assigned["unit_price"][-1] if assigned.get("unit_price") else None
        amount_pair = assigned["amount"][-1] if assigned.get("amount") else None
        discount_pair = assigned["discount"][-1] if assigned.get("discount") else None
        if len(matches) >= 3 and not (qty_pair and amount_pair):
            qty_pair, unit_pair, amount_pair = matches[-3], matches[-2], matches[-1]
        elif len(matches) == 2 and not (qty_pair and amount_pair) and not (unit_pair and amount_pair):
            continue
        elif len(matches) == 1 and amount_pair is None:
            continue
        total = amount_pair[1] if amount_pair else None
        if total is None:
            continue
        value_starts = [p[0].start() for p in (qty_pair, unit_pair, amount_pair, discount_pair) if p]
        desc_start = layout.get("description", 0) if layout else 0
        desc_end = min(value_starts) if value_starts else len(ln)
        desc = ln[desc_start:desc_end].strip(" -|\t:–—")
        if not desc or not re.search(r"[A-Za-zÀ-ÿ]", desc):
            continue
        quantity = qty_pair[1] if qty_pair else None
        unit_price = unit_pair[1] if unit_pair else None
        discount = discount_pair[1] if discount_pair else None
        it = LineItem(desc, quantity=quantity, unit_price=unit_price, line_total=total, discount=discount, page=pg)
        rate = re.search(r"(\d+(?:[.,]\d+)?)\s*%", ln)
        if rate:
            it.tax_rate = Decimal(rate.group(1).replace(",", "."))
        if quantity is not None and unit_price is not None:
            expected = (quantity * unit_price - (discount or Decimal(0))).quantize(CENT)
            if abs(expected - total) > CENT:
                it.reliable = False
                it.note = f"qty x unit price = {expected} but line total is {total}"
                inv.warnings.append(f"Unreliable line item '{desc[:40]}': {it.note}")
        items.append(it)
    return items
