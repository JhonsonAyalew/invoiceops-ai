"""Excel, CSV and PDF report generation. Every number comes from the selected job's database rows."""

from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extraction.numbers import fmt_money
from app.models import ALL_FIELDS, DATE_FIELDS, MONEY_FIELDS, Document, DuplicateCandidate, Invoice, Job, LineItem

NAVY, ACCENT, GREY = "#14213D", "#2A9D8F", "#6B7280"
INV_COLS = ["original_filename", "source_page", "extraction_method", "review_status"] + ALL_FIELDS
LINE_COLS = [
    "original_filename",
    "invoice_number",
    "line_no",
    "description",
    "quantity",
    "unit",
    "unit_price",
    "discount",
    "tax_rate",
    "tax_amount",
    "line_total",
    "reliable",
    "note",
]
_INJECT = ("=", "+", "-", "@", "\t", "\r")


def safe_text(v):
    """Neutralise spreadsheet formula injection in untrusted text."""
    if isinstance(v, str) and v and v[0] in _INJECT:
        return "'" + v
    return v


def review_label(inv: Invoice | None, doc: Document) -> str:
    if doc.status == "failed":
        return "failed"
    if doc.status == "duplicate":
        return "duplicate"
    if inv is not None and inv.reviewed:
        return "reviewed by operator"
    return "needs review" if doc.status == "needs_review" else "not reviewed"


class JobData:
    def __init__(self, s: Session, job_id: str):
        self.job = s.get(Job, job_id)
        self.docs = list(s.scalars(select(Document).where(Document.job_id == job_id).order_by(Document.created_at, Document.original_name)))
        self.inv = {i.document_id: i for i in s.scalars(select(Invoice).where(Invoice.job_id == job_id))}
        self.items = defaultdict(list)
        for li in s.scalars(
            select(LineItem)
            .join(Invoice, Invoice.id == LineItem.invoice_id)
            .where(Invoice.job_id == job_id)
            .order_by(LineItem.invoice_id, LineItem.position)
        ):
            self.items[li.invoice_id].append(li)
        self.dups = list(s.scalars(select(DuplicateCandidate).where(DuplicateCandidate.job_id == job_id)))
        self.names = {d.id: d.original_name for d in self.docs}
        self.rows = [(d, self.inv.get(d.id)) for d in self.docs if self.inv.get(d.id)]

    def stats(self) -> dict:
        c = Counter(d.status for d in self.docs)
        reviewed = sum(1 for _, i in self.rows if i.reviewed)
        methods = Counter((d.method or "n/a") for d, _ in self.rows)
        return {
            "uploaded": len(self.docs),
            "processed": c["processed"] + c["needs_review"] + c["reviewed"],
            "needs_review": sum(1 for d, i in self.rows if d.status == "needs_review" and not i.reviewed),
            "failed": c["failed"],
            "duplicates": len(self.dups) + c["duplicate"],
            "reviewed": reviewed,
            "methods": dict(methods),
        }

    def exceptions(self) -> list[dict]:
        out = []
        for d in self.docs:
            if d.status == "failed":
                out.append({"file": d.original_name, "type": "Failed document", "field": "", "detail": d.error or "processing failed"})
            if d.status == "duplicate":
                out.append(
                    {
                        "file": d.original_name,
                        "type": "Duplicate file",
                        "field": "",
                        "detail": f"identical to {self.names.get(d.duplicate_of, 'another file')}",
                    }
                )
            inv = self.inv.get(d.id)
            for iss in inv.issues if inv else []:
                if iss["severity"] == "info":
                    continue
                t = "Missing information" if iss["code"] == "missing_field" else "Validation"
                out.append({"file": d.original_name, "type": t, "field": iss.get("field") or "", "detail": iss["message"]})
        for x in self.dups:
            why = {"file": "identical file", "invoice": "same invoice number", "similar": "similar invoice"}.get(x.kind, x.kind)
            out.append(
                {
                    "file": self.names.get(x.doc_a, "?"),
                    "type": "Duplicate candidate",
                    "field": "",
                    "detail": f"{why}: matches {self.names.get(x.doc_b, '?')} (score {x.score:.2f})",
                }
            )
        return out


def _val(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()[:10]
    if isinstance(v, Decimal):
        return fmt_money(v)
    return v


# ------------------------------------------------------------------ CSV
def build_csv_invoices(data: JobData) -> bytes:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    w.writerow(INV_COLS)
    for d, i in data.rows:
        row = {
            "original_filename": d.original_name,
            "source_page": i.source_page,
            "extraction_method": i.extraction_method,
            "review_status": review_label(i, d),
            **{f: getattr(i, f) for f in ALL_FIELDS},
        }
        w.writerow(["" if row[c] is None else safe_text(str(_val(row[c]))) for c in INV_COLS])
    return buf.getvalue().encode("utf-8-sig")  # UTF-8 (with BOM so Excel detects the encoding)


def build_csv_lines(data: JobData) -> bytes:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(LINE_COLS)
    for d, i in data.rows:
        for n, li in enumerate(data.items.get(i.id, []), 1):
            vals = [
                d.original_name,
                i.invoice_number,
                n,
                li.description,
                li.quantity,
                li.unit,
                li.unit_price,
                li.discount,
                li.tax_rate,
                li.tax_amount,
                li.line_total,
                "yes" if li.reliable else "NO - verify",
                li.note,
            ]
            w.writerow(["" if v is None else safe_text(str(_val(v))) for v in vals])
    return buf.getvalue().encode("utf-8-sig")


# ------------------------------------------------------------------ XLSX
def _sheet(ws, headers, rows, money_cols=(), date_cols=(), widths=None):
    hf, fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor=NAVY[1:])
    ws.append(headers)
    for c in ws[1]:
        c.font, c.fill, c.alignment = hf, fill, Alignment(vertical="center", wrap_text=True)
    for r in rows:
        ws.append([safe_text(v) if isinstance(v, str) else v for v in r])
    ws.freeze_panes = "A2"
    if ws.max_row >= 1 and headers:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(ws.max_row, 1)}"
    for idx, h in enumerate(headers, 1):
        col = get_column_letter(idx)
        longest = max([len(str(h))] + [len(str(c.value)) for c in ws[col][1:200] if c.value is not None])
        ws.column_dimensions[col].width = min(max(12, longest + 2), (widths or {}).get(h, 45))
        for c in ws[col][1:]:
            if h in money_cols:
                c.number_format = "#,##0.00##"
            elif h in date_cols:
                c.number_format = "yyyy-mm-dd"


def build_xlsx(data: JobData) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Invoices"
    rows = []
    for d, i in data.rows:
        base = [d.original_name, i.source_page, i.extraction_method, review_label(i, d)]
        rows.append(base + [getattr(i, f) for f in ALL_FIELDS])
    _sheet(ws, INV_COLS, rows, money_cols=set(MONEY_FIELDS), date_cols=set(DATE_FIELDS))
    ws2 = wb.create_sheet("Line Items")
    lrows = []
    for d, i in data.rows:
        for n, li in enumerate(data.items.get(i.id, []), 1):
            lrows.append(
                [
                    d.original_name,
                    i.invoice_number,
                    n,
                    li.description,
                    li.quantity,
                    li.unit,
                    li.unit_price,
                    li.discount,
                    li.tax_rate,
                    li.tax_amount,
                    li.line_total,
                    "yes" if li.reliable else "NO - verify",
                    li.note,
                ]
            )
    _sheet(ws2, LINE_COLS, lrows, money_cols={"quantity", "unit_price", "discount", "tax_rate", "tax_amount", "line_total"})
    st = data.stats()
    ws3 = wb.create_sheet("Review Summary")
    srows = [
        ["Job", data.job.name],
        ["Reference", data.job.reference or ""],
        ["Generated (UTC)", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")],
        ["Documents uploaded", st["uploaded"]],
        ["Documents processed", st["processed"]],
        ["Needs review (not yet reviewed)", st["needs_review"]],
        ["Marked reviewed by operator", st["reviewed"]],
        ["Failed documents", st["failed"]],
        ["Duplicate candidates", st["duplicates"]],
    ]
    srows += [[f"Extraction method: {m}", n] for m, n in sorted(st["methods"].items())]
    _sheet(ws3, ["Metric", "Value"], srows)
    ws3.auto_filter.ref = None
    ws3.column_dimensions["A"].width = 38
    ws4 = wb.create_sheet("Exceptions")
    _sheet(ws4, ["File", "Type", "Field", "Detail"], [[e["file"], e["type"], e["field"], e["detail"]] for e in data.exceptions()])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# ------------------------------------------------------------------ PDF report
def _pdf_safe(v) -> str:
    """Built-in PDF fonts only cover Latin-1/WinAnsi; replace anything else rather than print boxes."""
    s = "" if v is None else str(v)
    return s.encode("cp1252", "replace").decode("cp1252")


def _esc(v) -> str:
    return _pdf_safe(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class _Numbered(canvas.Canvas):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        n = len(self._saved)
        for st in self._saved:
            self.__dict__.update(st)
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor(GREY))
            w, _ = self._pagesize
            self.drawRightString(w - 18 * mm, 10 * mm, f"Page {self._pageNumber} of {n}")
            super().showPage()
        super().save()


def build_pdf_report(data: JobData) -> bytes:
    buf = io.BytesIO()
    page = landscape(A4)
    job = data.job
    gen = datetime.now(timezone.utc).strftime("%d %B %Y")

    def deco(c, doc):
        w, h = page
        c.saveState()
        c.setFillColor(colors.HexColor(NAVY))
        c.rect(0, h - 14 * mm, w, 14 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(18 * mm, h - 9 * mm, "InvoiceOps AI")
        c.setFont("Helvetica", 9)
        c.drawRightString(w - 18 * mm, h - 9 * mm, _pdf_safe(f"Invoice Processing Report  |  {job.reference or job.name}"))
        c.setStrokeColor(colors.HexColor("#E5E7EB"))
        c.line(18 * mm, 14 * mm, w - 18 * mm, 14 * mm)
        c.setFillColor(colors.HexColor(GREY))
        c.setFont("Helvetica", 8)
        c.drawString(18 * mm, 10 * mm, f"Generated {gen}  |  Confidential - prepared for the client named in this order")
        c.restoreState()

    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=22, textColor=colors.HexColor(NAVY), spaceAfter=2)
    H2 = ParagraphStyle(
        "H2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=13, textColor=colors.HexColor(NAVY), spaceBefore=14, spaceAfter=6
    )
    B = ParagraphStyle("B", parent=ss["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13)
    SM = ParagraphStyle("SM", parent=B, fontSize=8, leading=10)
    SMR = ParagraphStyle("SMR", parent=SM, alignment=TA_RIGHT)
    MUT = ParagraphStyle("MUT", parent=B, textColor=colors.HexColor(GREY))

    def tbl(head, rows, widths, right=()):
        th = ParagraphStyle("th", parent=SM, textColor=colors.white)
        thr = ParagraphStyle("thr", parent=th, alignment=TA_RIGHT)
        data_ = [[Paragraph(f"<b>{_esc(h)}</b>", thr if j in right else th) for j, h in enumerate(head)]]
        for r in rows:
            data_.append([Paragraph(_esc(v), SMR if j in right else SM) for j, v in enumerate(r)])
        t = Table(data_, colWidths=widths, repeatRows=1, hAlign="LEFT")
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(NAVY)),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F4F6")]),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        return t

    st = data.stats()
    el = [
        Spacer(1, 4 * mm),
        Paragraph("Invoice Processing Report", H1),
        Paragraph(_esc(f"{job.name}" + (f"  -  Order {job.reference}" if job.reference else "")), MUT),
        Spacer(1, 4 * mm),
    ]
    kp = [
        ("Invoices uploaded", st["uploaded"]),
        ("Successfully processed", st["processed"]),
        ("Need review", st["needs_review"]),
        ("Failed", st["failed"]),
        ("Duplicate candidates", st["duplicates"]),
    ]
    cells = [
        [Paragraph(f'<font size="20" color="{NAVY}"><b>{v}</b></font><br/><font size="8" color="{GREY}">{k}</font>', B) for k, v in kp]
    ]
    kt = Table(cells, colWidths=[52 * mm] * 5)
    kt.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F9FAFB")),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    el += [kt, Paragraph("Processing summary", H2)]
    n_tot = st["uploaded"]
    review_txt = (
        f"{st['reviewed']} of {len(data.rows)} extracted invoices were marked as reviewed by the operator."
        if st["reviewed"]
        else "No invoices in this report have been marked as manually reviewed; values were extracted automatically and checked by automated validation only."
    )
    el.append(
        Paragraph(
            _esc(
                f"{n_tot} document(s) were received for this order. {st['processed']} were processed successfully, "
                f"{st['needs_review']} contain values flagged for attention, and {st['failed']} could not be processed. {review_txt}"
            ),
            B,
        )
    )
    el.append(Paragraph("Extraction methods", H2))
    el.append(
        tbl(["Method", "Documents"], [[m, n] for m, n in sorted(st["methods"].items())] or [["-", 0]], [70 * mm, 30 * mm], right=(1,))
    )
    # totals per currency (never mixed across currencies)
    sums: dict[str, Decimal] = defaultdict(Decimal)
    counts: Counter = Counter()
    for _, i in data.rows:
        if i.total_amount is not None:
            sums[i.currency or "(unknown)"] += i.total_amount
            counts[i.currency or "(unknown)"] += 1
    if sums:
        el.append(Paragraph("Totals by currency", H2))
        el.append(
            tbl(
                ["Currency", "Invoices", "Sum of invoice totals"],
                [[c, counts[c], f"{sums[c]:,.2f}"] for c in sorted(sums)],
                [40 * mm, 30 * mm, 60 * mm],
                right=(1, 2),
            )
        )
        el.append(Paragraph("Sums include only invoices where a total was found; currencies are never combined.", MUT))
    el.append(PageBreak())
    el.append(Paragraph("Invoice summary", H2))
    rows = []
    for d, i in data.rows:
        tot = "" if i.total_amount is None else f"{i.total_amount:,.2f}"
        rows.append(
            [
                i.supplier_name or "-",
                i.invoice_number or "-",
                i.invoice_date.isoformat() if i.invoice_date else "-",
                i.currency or "-",
                tot or "-",
                review_label(i, d),
                d.original_name,
            ]
        )
    el.append(
        tbl(
            ["Supplier", "Invoice no.", "Date", "Cur.", "Total", "Status", "Source file"],
            rows or [["No invoices extracted", "", "", "", "", "", ""]],
            [62 * mm, 36 * mm, 24 * mm, 14 * mm, 28 * mm, 34 * mm, 62 * mm],
            right=(4,),
        )
    )
    exc = data.exceptions()
    el.append(
        KeepTogether(
            [
                Paragraph("Processing exceptions", H2),
                Paragraph(
                    "Missing or uncertain fields, validation problems, failed documents and duplicate candidates."
                    if exc
                    else "No exceptions were recorded for this job.",
                    MUT,
                ),
            ]
        )
    )
    if exc:
        el.append(
            tbl(
                ["File", "Type", "Field", "Detail"],
                [[e["file"], e["type"], e["field"], e["detail"]] for e in exc],
                [60 * mm, 38 * mm, 28 * mm, 134 * mm],
            )
        )
    el += [
        Spacer(1, 8 * mm),
        Paragraph(
            "Extraction was performed automatically. Values flagged above should be verified against the source documents. "
            "Only invoices marked 'reviewed by operator' have been checked manually.",
            MUT,
        ),
    ]
    SimpleDocTemplate(
        buf,
        pagesize=page,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=22 * mm,
        bottomMargin=20 * mm,
        title=f"Invoice Processing Report - {job.name}",
        author="InvoiceOps AI",
    ).build(el, onFirstPage=deco, onLaterPages=deco, canvasmaker=_Numbered)
    return buf.getvalue()


KINDS = {
    "xlsx": ("xlsx", build_xlsx, "invoices"),
    "csv_invoices": ("csv", build_csv_invoices, "invoices"),
    "csv_line_items": ("csv", build_csv_lines, "line_items"),
    "pdf_report": ("pdf", build_pdf_report, "report"),
}
