import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PROOF = ROOT / "docs" / "proof"
sys.path.insert(0, str(BACKEND))

from app.config import AppSettings
from app.main import create_app
from fastapi.testclient import TestClient

INPUTS = [
    "invoice-fr-tenvi-ateliers-2026-65937.pdf",
    "invoice-us-marzel-systems-F2026-49858.pdf",
    "invoice-uk-elvel-trading-RE-66678.pdf",
    "invoice-us-velnov-consulting-2026-34850.pdf",
    "invoice-ch-novelbro-handels-0042368.pdf",
    "invoice-es-zelsol-servicios-F2025-10190-scanned.pdf",
    "invoice-fr-torlumin-conseil-2026-3571.pdf",
    "invoice-ch-tenquifan-technik-RE-84082.pdf",
    "invoice-de-dortorzel-technik-INV-2026-12730.pdf",
    "invoice-us-torlu-trading-0082649.pdf",
]
CORRECTION_TARGET = "invoice-es-zelsol-servicios-F2025-10190-scanned.pdf"
CORRECTIONS = {"total_amount": "48603.38"}
KINDS = ["xlsx", "csv_invoices", "csv_line_items", "pdf_report"]
LABELS = {
    "xlsx": "invoices.xlsx",
    "csv_invoices": "invoices.csv",
    "csv_line_items": "line_items.csv",
    "pdf_report": "processing_report.pdf",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--data-dir", default=str(Path(tempfile.gettempdir()) / "invoiceops-proof-demo")
    )
    ap.add_argument("--no-outputs", action="store_true")
    args = ap.parse_args()

    work = Path(args.data_dir).resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    db = work / "invoiceops.db"
    data = work / "data"

    os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"
    os.environ["DATA_DIR"] = str(data)
    os.environ["AI_PROVIDER"] = "none"

    settings = AppSettings(
        database_url=f"sqlite:///{db.as_posix()}",
        data_dir=str(data),
        sync_processing=True,
    )
    app = create_app(settings, create_tables=True)
    client = TestClient(app)

    r = client.post(
        "/api/jobs",
        json={
            "name": "InvoiceOps proof batch - 10 supplier PDFs",
            "reference": "PROOF-2026-001",
            "client_note": (
                "Ten supplier invoices (FR, UK, DE, CH, ES, US), including one scanned PDF "
                "and several embedded prompt-injection attempts. All values are extracted locally."
            ),
        },
    )
    r.raise_for_status()
    job = r.json()
    jid = job["id"]

    files = [
        ("files", (name, (PROOF / "outputs" / name).read_bytes(), "application/pdf"))
        for name in INPUTS
    ]
    r = client.post(f"/api/jobs/{jid}/upload", files=files)
    r.raise_for_status()
    added = r.json()["added"]

    r = client.post(f"/api/jobs/{jid}/process")
    r.raise_for_status()
    queued = r.json()["queued"]

    docs = client.get(f"/api/jobs/{jid}/documents").json()
    by_name = {d["name"]: d for d in docs}

    target = by_name[CORRECTION_TARGET]
    iid = target["invoice_id"]
    r = client.patch(f"/api/invoices/{iid}", json=CORRECTIONS)
    r.raise_for_status()
    invoice = r.json()
    corrections = client.get(f"/api/invoices/{iid}/corrections").json()
    r = client.post(f"/api/invoices/{iid}/review", json={"reviewed": True})
    r.raise_for_status()

    exports = client.post(f"/api/jobs/{jid}/exports", json={"kinds": KINDS}).json()
    by_kind = {e["kind"]: e for e in exports}

    out = PROOF / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    if not args.no_outputs:
        for kind, label in LABELS.items():
            blob = client.get(f"/api/exports/{by_kind[kind]['id']}/download").content
            (out / label).write_bytes(blob)

    status = client.get(f"/api/jobs/{jid}").json()["counts"]
    overview = client.get("/api/overview").json()
    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "job": {"id": jid, "name": job["name"], "reference": job["reference"]},
        "upload": {"submitted": len(INPUTS), "accepted": added},
        "processing": {
            "queued": queued,
            "counts": status,
            "overview": overview["counts"],
        },
        "extracted_invoices": [
            {
                "file": d["name"],
                "status": d["status"],
                "method": d.get("method"),
                "supplier": d.get("supplier_name"),
                "number": d.get("invoice_number"),
                "currency": d.get("currency"),
                "total": d.get("total_amount"),
                "issues": d.get("issue_count"),
            }
            for d in sorted(docs, key=lambda x: x["name"])
        ],
        "review": {
            "invoice": target["name"],
            "invoice_id": iid,
            "corrected_fields": [c["field"] for c in corrections],
            "reviewed": True,
            "original_total": invoice["original"]["total_amount"],
            "final_total": invoice["fields"]["total_amount"],
        },
        "deliverables": [
            {
                "kind": e["kind"],
                "filename": e["filename"],
                "size_bytes": e["size_bytes"],
            }
            for e in exports
        ],
    }
    if not args.no_outputs:
        (out / "demo_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"DEMO_DATA_DIR={work}")


if __name__ == "__main__":
    main()
