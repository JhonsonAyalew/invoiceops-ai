"""Generate synthetic test invoices (no real client data)."""

from __future__ import annotations
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def _pdf(path: Path, lines: list[str]):
    c = canvas.Canvas(str(path), pagesize=A4)
    y = 800
    for ln in lines:
        if ln == "---PAGE---":
            c.showPage()
            y = 800
            continue
        c.setFont("Helvetica", 11)
        c.drawString(50, y, ln)
        y -= 18
    c.save()


EN = [
    "Acme Supplies Ltd",
    "12 Market Street, London EC1A 1BB",
    "VAT ID: GB123456789",
    "INVOICE",
    "Invoice No: INV-2024-0042",
    "Invoice Date: March 3, 2024",
    "Due Date: April 2, 2024",
    "PO Number: PO-7788",
    "",
    "Bill To:",
    "Globex Corporation",
    "99 Broadway, New York",
    "",
    "Description    Qty    Unit Price    Amount",
    "Widget A    10    $12.50    $125.00",
    "Gadget B    2    $1,250.00    $2,500.00",
    "Subtotal: $2,625.00",
    "Shipping: $25.00",
    "Sales Tax (8%): $210.00",
    "Total: $2,860.00",
    "Payment Terms: Net 30",
]
DE = [
    "Müller Handels GmbH",
    "Hauptstraße 5, 10115 Berlin",
    "USt-IdNr: DE123456789",
    "Rechnung",
    "Rechnungsnummer: RE-2024-118",
    "Rechnungsdatum: 15.03.2024",
    "Fällig am: 14.04.2024",
    "Rechnung an:",
    "Kunde AG",
    "Lindenweg 3, 80331 München",
    "Beschreibung    Menge    Einzelpreis    Gesamt",
    "Schraube M8    1.000    0,15 €    150,00 €",
    "Montagearbeit    12    85,50 €    1.026,00 €",
    "Zwischensumme: 1.176,00 €",
    "MwSt 19%: 223,44 €",
    "Gesamtbetrag: 1.399,44 €",
]
ZERO = [
    "Nordic Export AB",
    "Storgatan 1, Stockholm",
    "INVOICE",
    "Invoice #: NX-5001",
    "Invoice Date: 2024-05-10",
    "Due Date: 2024-06-09",
    "Bill To:",
    "Intra Corp",
    "1 Rue X, Paris",
    "Description    Qty    Unit Price    Total",
    "Consulting    8    EUR 100.00    EUR 800.00",
    "Subtotal: EUR 800.00",
    "VAT (0%): EUR 0.00",
    "Total: EUR 800.00",
]
BAD_LINE = EN[:14] + ["Widget A    10    $12.50    $130.00", "Subtotal: $130.00", "Total: $130.00"]


ODD = ["Zeta Parts Inc", "TAX INVOICE", "Ref A-99871", "Issued 5 June 2024", "Amount payable 1,000.00 USD"]
MULTI = EN[:14] + [
    "Widget A    10    $12.50    $125.00",
    "---PAGE---",
    "Gadget B    2    $1,250.00    $2,500.00",
    "Subtotal: $2,625.00",
    "Shipping: $25.00",
    "Sales Tax (8%): $210.00",
    "Total: $2,860.00",
]


def build(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    _pdf(out / "en_usd.pdf", EN)
    _pdf(out / "de_eur.pdf", DE)
    _pdf(out / "zero_tax_eur.pdf", ZERO)
    _pdf(out / "bad_line_item.pdf", BAD_LINE)
    _pdf(out / "odd_labels.pdf", ODD)
    _pdf(out / "multi_page.pdf", MULTI)
    (out / "en_usd_copy.pdf").write_bytes((out / "en_usd.pdf").read_bytes())
    (out / "corrupted.pdf").write_bytes(b"%PDF-1.4\nthis is not a real pdf")
    (out / "not_pdf.pdf").write_bytes(b"hello")
    # scanned: render to image, save image-only PDF
    from pdf2image import convert_from_path

    img = convert_from_path(str(out / "en_usd.pdf"), dpi=200)[0].convert("L")
    img.save(out / "scanned_en.pdf", "PDF", resolution=200)


if __name__ == "__main__":
    build(Path(__file__).resolve().parent.parent / "samples")
