from datetime import date
from decimal import Decimal as D
import pytest
from app.config import OcrSettings
from app.extraction import ocr
from app.extraction.duplicates import find_duplicates
from app.extraction.pipeline import extract_document
from tests.make_samples import build

S = OcrSettings.from_env()


@pytest.fixture(scope="session")
def samples(tmp_path_factory):
    d = tmp_path_factory.mktemp("samples")
    build(d)
    return d


def test_english_invoice(samples):
    r = extract_document(samples / "en_usd.pdf", S)
    g = r.parsed.get
    assert r.method == "native"
    assert g("invoice_number") == "INV-2024-0042"
    assert g("invoice_date") == date(2024, 3, 3) and g("due_date") == date(2024, 4, 2)
    assert g("currency") == "USD" and g("po_number") == "PO-7788"
    assert g("subtotal") == D("2625.00") and g("tax_amount") == D("210.00")
    assert g("shipping") == D("25.00") and g("total_amount") == D("2860.00")
    assert g("supplier_name") == "Acme Supplies Ltd" and g("customer_name") == "Globex Corporation"
    assert g("supplier_tax_id") == "GB123456789"
    assert [i.line_total for i in r.parsed.line_items] == [D("125.00"), D("2500.00")]
    assert r.parsed.line_items[1].unit_price == D("1250.00")
    assert all(i.reliable for i in r.parsed.line_items)
    assert r.status == "processed", r.issues


def test_german_locale(samples):
    r = extract_document(samples / "de_eur.pdf", S)
    g = r.parsed.get
    assert r.parsed.decimal_sep == "," and g("currency") == "EUR"
    assert g("invoice_number") == "RE-2024-118" and g("invoice_date") == date(2024, 3, 15)
    assert g("due_date") == date(2024, 4, 14)
    assert g("subtotal") == D("1176.00") and g("tax_amount") == D("223.44") and g("total_amount") == D("1399.44")
    li = r.parsed.line_items
    assert li[0].quantity == D("1000") and li[0].unit_price == D("0.15") and li[0].line_total == D("150.00")
    assert li[1].unit_price == D("85.50") and li[1].line_total == D("1026.00")
    assert r.status == "processed", r.issues


def test_zero_tax_is_zero_not_missing(samples):
    r = extract_document(samples / "zero_tax_eur.pdf", S)
    assert r.parsed.get("tax_amount") == D("0.00") and r.parsed.get("tax_amount") is not None
    assert r.parsed.get("total_amount") == D("800.00") and r.parsed.get("currency") == "EUR"
    assert r.parsed.get("invoice_date") == date(2024, 5, 10)
    assert r.status == "processed", r.issues


def test_unreliable_line_item_flagged(samples):
    r = extract_document(samples / "bad_line_item.pdf", S)
    assert r.parsed.line_items and not r.parsed.line_items[0].reliable
    assert any(i["code"] == "line_item_unreliable" for i in r.issues)
    assert r.status == "needs_review"


def test_failed_documents(samples):
    assert extract_document(samples / "corrupted.pdf", S).status == "failed"
    r = extract_document(samples / "not_pdf.pdf", S)
    assert r.status == "failed" and r.error == "not_a_pdf"


def test_duplicates(samples):
    recs = []
    for i, n in enumerate(["en_usd.pdf", "en_usd_copy.pdf", "de_eur.pdf"]):
        r = extract_document(samples / n, S)
        recs.append(
            {
                "id": i,
                "sha256": r.sha256,
                "supplier_name": r.parsed.get("supplier_name"),
                "invoice_number": r.parsed.get("invoice_number"),
                "total_amount": r.parsed.get("total_amount"),
            }
        )
    d = find_duplicates(recs)
    assert len(d) == 1 and d[0]["kind"] == "file" and {d[0]["a"], d[0]["b"]} == {0, 1}


def test_ocr_status_reports():
    st = ocr.check_ocr(S)
    assert st.package_found and st.det_model_found and st.rec_model_found and st.poppler_found
    assert st.model == "PP-OCRv6 Medium" and st.ready
    bad = ocr.check_ocr(OcrSettings(model_dir="C:\\nonexistent\\paddle_models"))
    assert not bad.ready and any("PP-OCRv6" in p for p in bad.problems)


def test_scanned_pdf_uses_ocr(samples):
    r = extract_document(samples / "scanned_en.pdf", S)
    assert r.method == "ocr" and r.ocr_pages == [1]
    g = r.parsed.get
    assert g("invoice_number") == "INV-2024-0042"
    assert g("total_amount") == D("2860.00")
    assert any(i["code"] == "ocr_used" for i in r.issues)  # OCR use is always disclosed
    assert r.status == "processed"  # totals reconcile, so no warnings
