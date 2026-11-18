import json
from pathlib import Path

from openpyxl import load_workbook
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
PROOF = ROOT / "docs" / "proof"
OUTPUTS = PROOF / "outputs"
SHOTS = PROOF / "screenshots"
LOGS = PROOF / "logs"


def summary():
    return json.loads((OUTPUTS / "demo_summary.json").read_text(encoding="utf-8"))


def test_demo_summary_describes_real_workflow():
    s = summary()
    assert s["upload"] == {"submitted": 10, "accepted": 10}
    assert s["processing"]["queued"] == 10
    assert s["processing"]["counts"]["total"] == 10
    assert s["processing"]["counts"]["duplicate"] == 0
    assert s["processing"]["counts"]["failed"] == 0
    assert s["processing"]["counts"]["reviewed"] == 1
    assert s["processing"]["counts"]["processed"] == 3
    assert s["processing"]["counts"]["needs_review"] == 6
    assert [i["method"] for i in s["extracted_invoices"]].count("ocr") == 1
    assert s["review"]["corrected_fields"] == ["total_amount"]
    assert s["review"]["original_total"] is None
    assert s["review"]["final_total"] == "48603.38"
    assert {e["kind"] for e in s["deliverables"]} == {"xlsx", "csv_invoices", "csv_line_items", "pdf_report"}


def test_exported_files_are_readable_and_consistent():
    s = summary()
    for e in s["deliverables"]:
        assert e["size_bytes"] > 0
    assert (OUTPUTS / "invoice-es-zelsol-servicios-F2025-10190-scanned.pdf").read_bytes().startswith(b"%PDF")

    wb = load_workbook(OUTPUTS / "invoices.xlsx", data_only=True)
    assert wb.sheetnames == ["Invoices", "Line Items", "Review Summary", "Exceptions"]
    assert wb["Invoices"].max_row == 11
    assert any(row[0].value == "invoice-es-zelsol-servicios-F2025-10190-scanned.pdf" for row in wb["Invoices"].iter_rows(min_row=2))

    csv = (OUTPUTS / "invoices.csv").read_text(encoding="utf-8-sig")
    assert "48603.38" in csv
    assert "Zelsol Servicios S.A." in csv
    assert "Maintenance du site web, mensuelle" in (OUTPUTS / "line_items.csv").read_text(encoding="utf-8-sig")

    reader = PdfReader(OUTPUTS / "processing_report.pdf")
    text = " ".join(" ".join(page.extract_text().split()) for page in reader.pages)
    assert "InvoiceOps AI" in text
    assert "PROOF-2026-001" in text
    assert "Zelsol Servicios S.A." in text
    assert "1 of 10 extracted invoices were marked as reviewed by the operator" in text


def test_proof_screenshots_and_logs_exist():
    manifest = json.loads((LOGS / "screenshots.json").read_text(encoding="utf-8"))
    assert manifest["viewport"] == "1440x900"
    for item in manifest["files"]:
        path = SHOTS / item["file"]
        assert path.is_file() and path.stat().st_size == item["bytes"]
        assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    report = json.loads((LOGS / "verification.json").read_text(encoding="utf-8"))
    assert report["summary"]["total"] == 10
    assert len(report["checks"]) == 10
    for check in report["checks"]:
        assert (ROOT / check["log"]).is_file()
