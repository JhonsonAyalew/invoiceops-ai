import io
import json
import zipfile
from datetime import date
from decimal import Decimal as D
from pathlib import Path

from openpyxl import load_workbook
from pypdf import PdfReader

from app.ai.base import AIProvider


def up(client, job_id, samples, names):
    files = [("files", (n, (samples / n).read_bytes(), "application/pdf")) for n in names]
    r = client.post(f"/api/jobs/{job_id}/upload", files=files)
    assert r.status_code == 201, r.text
    return r.json()


def mkjob(client, **kw):
    r = client.post("/api/jobs", json={"name": "Fiverr order A", "reference": "FO-1001", **kw})
    assert r.status_code == 201
    return r.json()["id"]


def docs(client, jid, status=None):
    r = client.get(f"/api/jobs/{jid}/documents", params={"status": status} if status else None)
    assert r.status_code == 200
    return {d["name"]: d for d in r.json()}


ALL = [
    "en_usd.pdf",
    "de_eur.pdf",
    "zero_tax_eur.pdf",
    "scanned_en.pdf",
    "bad_line_item.pdf",
    "multi_page.pdf",
    "corrupted.pdf",
    "en_usd_copy.pdf",
]


def test_full_workflow(make_client, samples):
    c = make_client()
    jid = mkjob(c)
    r = up(c, jid, samples, ALL)
    assert r["added"] == 8
    d = docs(c, jid)
    assert d["corrupted.pdf"]["status"] == "failed" and d["corrupted.pdf"]["error"].startswith("corrupted")
    assert d["en_usd_copy.pdf"]["status"] == "duplicate" and d["en_usd_copy.pdf"]["duplicate_of"] == d["en_usd.pdf"]["id"]
    assert d["multi_page.pdf"]["pages"] == 2 and d["en_usd.pdf"]["status"] == "queued"
    # text file is rejected as unsupported
    c.post(f"/api/jobs/{jid}/upload", files=[("files", ("notes.txt", b"hello", "text/plain"))])
    assert docs(c, jid)["notes.txt"]["error"] == "unsupported_file_type"
    # process everything
    assert c.post(f"/api/jobs/{jid}/process").json()["queued"] == 6
    assert c.post(f"/api/jobs/{jid}/process").status_code == 409
    pr = c.get(f"/api/jobs/{jid}/progress").json()
    assert pr["percent"] == 100 and not pr["active"]
    d = docs(c, jid)
    assert d["en_usd.pdf"]["status"] == "processed" and d["en_usd.pdf"]["total_amount"] == "2860.00"
    assert d["de_eur.pdf"]["total_amount"] == "1399.44" and d["de_eur.pdf"]["currency"] == "EUR"
    assert d["scanned_en.pdf"]["method"] == "ocr" and d["scanned_en.pdf"]["invoice_number"] == "INV-2024-0042"
    assert d["multi_page.pdf"]["total_amount"] == "2860.00" and d["multi_page.pdf"]["method"] == "native"
    assert d["bad_line_item.pdf"]["status"] == "needs_review"
    # invoice detail
    inv = c.get(f"/api/invoices/{d['zero_tax_eur.pdf']['invoice_id']}").json()
    assert inv["fields"]["tax_amount"] == "0.00" and inv["fields"]["invoice_date"] == "2024-05-10"
    assert inv["line_items"][0]["unit_price"] == "100.00"
    # corrections: validation, audit trail, originals preserved
    iid = d["bad_line_item.pdf"]["invoice_id"]
    assert c.patch(f"/api/invoices/{iid}", json={"total_amount": "abc"}).status_code == 422
    assert c.patch(f"/api/invoices/{iid}", json={"invoice_date": "03/04/2024"}).status_code == 422
    assert c.patch(f"/api/invoices/{iid}", json={"nope": "x"}).status_code == 422
    r = c.patch(f"/api/invoices/{iid}", json={"total_amount": "1.234,50", "currency": "usd", "po_number": ""}).json()
    assert set(r["changed"]) == {"total_amount", "po_number"} and r["fields"]["total_amount"] == "1234.50"
    assert r["original"]["total_amount"] == "130.00" and "total_amount" in r["edited_fields"]
    assert [x["field"] for x in c.get(f"/api/invoices/{iid}/corrections").json()] == ["total_amount", "po_number"]
    r = c.put(
        f"/api/invoices/{iid}/line-items",
        json=[{"description": "Widget A", "quantity": "10", "unit_price": "12.50", "line_total": "125.00"}],
    ).json()
    assert r["line_items"][0]["reliable"] is True
    # review
    r = c.post(f"/api/invoices/{iid}/review", json={"reviewed": True}).json()
    assert r["reviewed"] and docs(c, jid, "reviewed")["bad_line_item.pdf"]
    assert c.get(f"/api/jobs/{jid}").json()["counts"]["reviewed"] == 1
    # duplicates
    # exports
    ex = c.post(f"/api/jobs/{jid}/exports", json={"kinds": ["xlsx", "csv_invoices", "csv_line_items", "pdf_report"]}).json()
    assert len(ex) == 4
    files = {e["kind"]: c.get(f"/api/exports/{e['id']}/download") for e in ex}
    assert all(f.status_code == 200 for f in files.values())
    wb = load_workbook(io.BytesIO(files["xlsx"].content))
    assert wb.sheetnames == ["Invoices", "Line Items", "Review Summary", "Exceptions"]
    ws = wb["Invoices"]
    hdr = [x.value for x in ws[1]]
    assert ws.freeze_panes == "A2" and ws.auto_filter.ref
    rows = {r[0].value: {h: r[i].value for i, h in enumerate(hdr)} for r in ws.iter_rows(min_row=2)}
    assert set(rows) == {"en_usd.pdf", "de_eur.pdf", "zero_tax_eur.pdf", "scanned_en.pdf", "bad_line_item.pdf", "multi_page.pdf"}
    assert D(str(rows["en_usd.pdf"]["total_amount"])) == D("2860") and rows["en_usd.pdf"]["invoice_date"].date() == date(2024, 3, 3)
    assert rows["bad_line_item.pdf"]["review_status"] == "reviewed by operator" and rows["en_usd.pdf"]["review_status"] == "not reviewed"
    assert any(r[1].value == "Failed document" for r in wb["Exceptions"].iter_rows(min_row=2))
    assert any(r[1].value == "Duplicate file" for r in wb["Exceptions"].iter_rows(min_row=2))
    csv_txt = files["csv_invoices"].content.decode("utf-8-sig")
    assert csv_txt.splitlines()[0].startswith("original_filename,source_page") and "2024-03-03" in csv_txt and "2860.00" in csv_txt
    assert "Widget A" in files["csv_line_items"].content.decode("utf-8-sig")
    pdf = PdfReader(io.BytesIO(files["pdf_report"].content))
    text = " ".join(" ".join(p.extract_text().split()) for p in pdf.pages)
    assert "InvoiceOps AI" in text and "FO-1001" in text and "Page 1 of" in text and "Acme Supplies Ltd" in text
    assert "1 of 6 extracted invoices were marked as reviewed by the operator" in text
    assert c.get(f"/api/jobs/{jid}/exports").json()[0]["filename"].startswith("FO-1001_")


def test_formula_injection_neutralised(make_client, samples):
    c = make_client()
    jid = mkjob(c)
    up(c, jid, samples, ["en_usd.pdf"])
    c.post(f"/api/jobs/{jid}/process")
    iid = docs(c, jid)["en_usd.pdf"]["invoice_id"]
    evil = '=HYPERLINK("http://evil","x")'
    c.patch(f"/api/invoices/{iid}", json={"supplier_name": evil, "notes": "@SUM(1)"})
    ex = {e["kind"]: e for e in c.post(f"/api/jobs/{jid}/exports", json={"kinds": ["xlsx", "csv_invoices"]}).json()}
    wb = load_workbook(io.BytesIO(c.get(f"/api/exports/{ex['xlsx']['id']}/download").content))
    cell = [x for r in wb["Invoices"].iter_rows(min_row=2) for x in r if isinstance(x.value, str) and "HYPERLINK" in x.value][0]
    assert cell.value.startswith("'=") and cell.data_type != "f"
    assert "'=HYPERLINK" in c.get(f"/api/exports/{ex['csv_invoices']['id']}/download").content.decode("utf-8-sig")


def test_job_isolation_and_delete(make_client, samples):
    c = make_client()
    a, b = mkjob(c), mkjob(c, name="Order B", reference="FO-2")
    up(c, a, samples, ["en_usd.pdf", "de_eur.pdf"])
    up(c, b, samples, ["en_usd.pdf"])  # same file in another job is NOT a duplicate
    assert docs(c, b)["en_usd.pdf"]["status"] == "queued"
    c.post(f"/api/jobs/{a}/process")
    c.post(f"/api/jobs/{b}/process")
    assert set(docs(c, a)) == {"en_usd.pdf", "de_eur.pdf"} and set(docs(c, b)) == {"en_usd.pdf"}
    da, db_ = docs(c, a)["en_usd.pdf"], docs(c, b)["en_usd.pdf"]
    assert da["id"] != db_["id"] and c.get(f"/api/documents/{da['id']}/file").content.startswith(b"%PDF")
    c.post(f"/api/jobs/{a}/exports", json={"kinds": ["xlsx"]})
    wb = load_workbook(io.BytesIO(c.get(f"/api/exports/{c.get(f'/api/jobs/{a}/exports').json()[0]['id']}/download").content))
    assert wb["Invoices"].max_row == 3  # header + 2 invoices of job A only
    root = Path(c.app_.state.ctx.settings.data_dir) / "jobs"
    assert (root / a).exists()
    assert c.delete(f"/api/jobs/{a}").status_code == 204
    assert not (root / a).exists() and (root / b).exists()
    assert c.get(f"/api/jobs/{a}").status_code == 404 and c.get(f"/api/documents/{da['id']}/file").status_code == 404
    assert c.get(f"/api/invoices/{da['invoice_id']}").status_code == 404
    assert len(c.get("/api/jobs").json()) == 1 and docs(c, b)["en_usd.pdf"]["status"] == "processed"
    ov = c.get("/api/overview").json()
    assert ov["jobs"] == 1 and ov["documents"] == 1


def test_zip_upload_and_path_traversal(make_client, samples):
    c = make_client()
    jid = mkjob(c)
    buf = io.BytesIO()
    pdf = (samples / "en_usd.pdf").read_bytes()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("invoices/a.pdf", pdf)
        z.writestr("../../evil.pdf", (samples / "de_eur.pdf").read_bytes())
        z.writestr("/abs/path/zero.pdf", (samples / "zero_tax_eur.pdf").read_bytes())
        z.writestr("readme.txt", b"ignore me")
    r = c.post(f"/api/jobs/{jid}/upload", files=[("files", ("batch.zip", buf.getvalue(), "application/zip"))])
    assert r.status_code == 201 and r.json()["added"] == 3
    assert set(docs(c, jid)) == {"a.pdf", "evil.pdf", "zero.pdf"}  # names reduced to basenames, display only
    data = Path(c.app_.state.ctx.settings.data_dir).resolve()
    stored = [p for p in data.rglob("*") if p.is_file()]
    assert all(data in p.parents for p in stored) and not any(p.name == "evil.pdf" for p in stored)
    assert not (data.parent / "evil.pdf").exists() and not Path("/abs/path/zero.pdf").exists()
    # bad / oversized zips are reported, not crashed on
    r = c.post(f"/api/jobs/{jid}/upload", files=[("files", ("broken.zip", b"PK\x03\x04garbage", "application/zip"))])
    assert r.status_code == 201 and docs(c, jid)["broken.zip"]["error"] == "bad_zip"
    c2 = make_client(max_zip_files=2)
    j2 = mkjob(c2)
    r = c2.post(f"/api/jobs/{j2}/upload", files=[("files", ("batch.zip", buf.getvalue(), "application/zip"))])
    assert docs(c2, j2)["batch.zip"]["error"] == "zip_too_many_files"


def test_upload_size_limit(make_client, samples):
    c = make_client(max_upload_mb=0)
    jid = mkjob(c)
    up(c, jid, samples, ["en_usd.pdf"])
    assert docs(c, jid)["en_usd.pdf"]["error"] == "file_too_large"
    data = Path(c.app_.state.ctx.settings.data_dir)
    assert not list((data / "jobs" / jid / "docs").iterdir())  # partial file cleaned up


def test_retry_failed_document(make_client, samples, monkeypatch):
    c = make_client()
    jid = mkjob(c)
    up(c, jid, samples, ["en_usd.pdf"])
    from app.services import processing

    real = processing.extract_document
    monkeypatch.setattr(processing, "extract_document", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    c.post(f"/api/jobs/{jid}/process")
    d = docs(c, jid)["en_usd.pdf"]
    assert d["status"] == "failed" and d["error"].startswith("internal_error")
    monkeypatch.setattr(processing, "extract_document", real)
    assert c.post(f"/api/documents/{d['id']}/retry").json()["queued"] == 1
    assert docs(c, jid)["en_usd.pdf"]["status"] == "processed"


class FakeCloud(AIProvider):
    name, is_cloud, calls = "cloudtest", True, 0

    def complete_json(self, system, user):
        FakeCloud.calls += 1
        return json.dumps({"invoice_number": "A-99871", "invoice_date": "2024-06-05", "total_amount": "1000.00", "currency": "USD"})


def test_cloud_ai_requires_consent(make_client, samples, monkeypatch):
    from app.services import processing

    monkeypatch.setattr(processing, "get_provider", lambda s: FakeCloud())
    FakeCloud.calls = 0
    c = make_client()
    j1 = mkjob(c, use_ai=True)
    up(c, j1, samples, ["odd_labels.pdf"])
    c.post(f"/api/jobs/{j1}/process")
    inv = c.get(f"/api/invoices/{docs(c, j1)['odd_labels.pdf']['invoice_id']}").json()
    assert FakeCloud.calls == 0 and inv["fields"]["invoice_number"] is None
    assert any(i["code"] == "ai_skipped_no_consent" for i in inv["issues"])
    assert c.post(f"/api/jobs/{j1}/consent", json={"provider": "cloudtest", "acknowledge": False}).status_code == 422
    j2 = mkjob(c, use_ai=True)
    assert (
        c.post(f"/api/jobs/{j2}/consent", json={"provider": "cloudtest", "acknowledge": True}).json()["ai_consent_provider"] == "cloudtest"
    )
    up(c, j2, samples, ["odd_labels.pdf"])
    c.post(f"/api/jobs/{j2}/process")
    inv = c.get(f"/api/invoices/{docs(c, j2)['odd_labels.pdf']['invoice_id']}").json()
    assert (
        FakeCloud.calls == 1 and inv["fields"]["invoice_number"] == "A-99871" and inv["meta"]["invoice_number"]["source"] == "ai:cloudtest"
    )
    assert inv["fields"]["total_amount"] == "1000.00" and inv["extraction_method"].endswith("+ai")
    # consent for job 2 does not carry over to job 3
    j3 = mkjob(c, use_ai=True)
    up(c, j3, samples, ["odd_labels.pdf"])
    c.post(f"/api/jobs/{j3}/process")
    assert FakeCloud.calls == 1
    c.delete(f"/api/jobs/{j2}/consent")
    assert c.get(f"/api/jobs/{j2}").json()["ai_consent_provider"] is None


def test_auth_token(make_client, samples):
    c = make_client(admin_token="s3cret")
    assert c.get("/api/jobs").status_code == 401
    assert c.get("/api/jobs", headers={"X-Admin-Token": "wrong"}).status_code == 401
    assert c.get("/api/jobs", headers={"X-Admin-Token": "s3cret"}).status_code == 200
    assert c.get("/api/jobs?token=s3cret").status_code == 200


def test_settings_and_secrets(make_client):
    c = make_client()
    r = c.get("/api/settings")
    assert r.status_code == 200
    ai_settings = r.json()["ai"]
    assert set(ai_settings) == {
        "provider",
        "is_cloud",
        "ollama_url",
        "ollama_model",
        "groq_base_url",
        "groq_model",
        "groq_key_configured",
    }
    assert "groq_api_key" not in ai_settings
    st = r.json()["ocr_status"]
    assert st["package_found"] and st["det_model_found"] and st["rec_model_found"]
    assert st["model"] == "PP-OCRv6 Medium" and "eng" in st["languages"]
    assert c.put("/api/settings/ocr", json={"languages": ["eng", "xx"]}).status_code == 422
    assert c.put("/api/settings/ocr", json={"device": "tpu"}).status_code == 422
    assert c.put("/api/settings/ocr", json={"dpi": 10}).status_code == 422
    assert c.put("/api/settings/ai", json={"provider": "skynet"}).status_code == 422
    r = c.put("/api/settings/ocr", json={"languages": ["eng", "deu"], "dpi": 200, "device": "cpu"}).json()
    assert r["ocr"]["languages"] == ["eng", "deu"] and r["ocr"]["dpi"] == 200
    assert r["ocr_status"]["device"] == "cpu"
    assert c.put("/api/settings/ai", json={"provider": "ollama"}).json()["ai"]["provider"] == "ollama"
    assert c.put("/api/settings/ai", json={"provider": "groq", "groq_api_key": "leak"}).json()["ai"]["provider"] == "groq"
    assert "groq_api_key" not in c.get("/api/settings").json()["ai"]
    assert c.put("/api/settings/ai", json={"groq_base_url": "http://insecure"}).status_code == 422
    assert c.put("/api/settings/ai", json={"provider": "none"}).json()["ai"]["provider"] == "none"
    assert c.post("/api/settings/ai/test").json()["ok"] is True


def test_retention_purge(make_client, samples):
    from datetime import datetime, timedelta, timezone
    from app.models import Job

    c = make_client(retention_days=1)
    j_old, j_new = mkjob(c), mkjob(c)
    up(c, j_old, samples, ["en_usd.pdf"])
    with c.app_.state.ctx.sf() as s:
        s.get(Job, j_old).created_at = datetime.now(timezone.utc) - timedelta(days=3)
        s.commit()
    assert c.post("/api/maintenance/purge").json()["deleted_jobs"] == [j_old]
    assert not (Path(c.app_.state.ctx.settings.data_dir) / "jobs" / j_old).exists()
    assert [j["id"] for j in c.get("/api/jobs").json()] == [j_new]


def test_job_validation(make_client):
    c = make_client()
    assert c.post("/api/jobs", json={"name": ""}).status_code == 422
    assert c.get("/api/jobs/not-a-valid-id").status_code == 404
    assert c.get("/api/jobs/" + "0" * 32 + "/documents").status_code == 404
