import json
import os
import sys
import threading
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PROOF = ROOT / "docs" / "proof"
SHOTS = PROOF / "screenshots"
LOGS = PROOF / "logs"
sys.path.insert(0, str(BACKEND))

import uvicorn
from app.config import AppSettings
from app.main import create_app
from openpyxl import load_workbook
from pdf2image import convert_from_path
from playwright.sync_api import sync_playwright


def render_workbook(path, target, browser):
    wb = load_workbook(path, data_only=True)
    parts = [
        "<style>body{font:12px Segoe UI,Arial;color:#182033;margin:24px;background:#fff}h1{font-size:20px;margin:0 0 4px}p{color:#63708c;margin:0 0 18px}h2{font-size:14px;margin:18px 0 6px}table{border-collapse:collapse;width:100%;font-size:11px}th{background:#1f2940;color:#fff;text-align:left;padding:5px 6px}td{border-bottom:1px solid #e4e8f0;padding:4px 6px;white-space:nowrap}tr:nth-child(even){background:#f7f9fc}</style>",
        "<h1>InvoiceOps AI - exported Excel workbook</h1><p>Rendered directly from docs/proof/outputs/invoices.xlsx</p>",
    ]
    for ws in wb.worksheets:
        parts.append(f"<h2>{ws.title}</h2><table>")
        rows = list(ws.iter_rows(values_only=True))
        if rows:
            parts.append(
                "<tr>"
                + "".join(f"<th>{c if c is not None else ''}</th>" for c in rows[0])
                + "</tr>"
            )
            for row in rows[1:26]:
                parts.append(
                    "<tr>"
                    + "".join(f"<td>{c if c is not None else ''}</td>" for c in row)
                    + "</tr>"
                )
        parts.append("</table>")
    page = browser.new_page(
        viewport={"width": 1440, "height": 1000}, device_scale_factor=1
    )
    page.set_content("".join(parts))
    page.screenshot(path=str(target), full_page=True)
    page.close()


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--data-dir",
        default=str(Path(os.environ.get("TEMP", "/tmp")) / "invoiceops-proof-demo"),
    )
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--channel", default="chrome")
    args = ap.parse_args()

    summary = json.loads(
        (PROOF / "outputs" / "demo_summary.json").read_text(encoding="utf-8")
    )
    jid = summary["job"]["id"]
    iid = summary["review"]["invoice_id"]
    work = Path(args.data_dir).resolve()
    db = work / "invoiceops.db"

    os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"
    os.environ["DATA_DIR"] = str(work / "data")
    os.environ["AI_PROVIDER"] = "none"

    settings = AppSettings(
        database_url=f"sqlite:///{db.as_posix()}", data_dir=str(work / "data")
    )
    app = create_app(settings, create_tables=False)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{args.port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/api/health", timeout=1).read()
            break
        except OSError:
            time.sleep(0.1)

    SHOTS.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    manifest = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel=args.channel, headless=True, args=["--force-color-profile=srgb"]
        )
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1,
            locale="en-US",
        )
        page = ctx.new_page()
        pages = [
            ("01_overview.png", "/", "Recent jobs"),
            ("02_jobs.png", "/jobs", "InvoiceOps proof batch"),
            ("03_new_job.png", "/jobs/new", "Create job"),
            ("04_results.png", f"/jobs/{jid}/results", summary["review"]["invoice"]),
            ("05_review.png", f"/jobs/{jid}/review/{iid}", "Supplier name"),
            ("06_export_center.png", "/exports", "Generated files"),
            ("07_settings_ocr.png", "/settings/ocr", "Installation status"),
            ("08_job_exports.png", f"/jobs/{jid}/exports", "Generated files"),
        ]
        for name, route, text in pages:
            page.goto(base + "/", wait_until="networkidle")
            if route != "/":
                page.evaluate(
                    "r => { history.pushState({}, '', r); window.dispatchEvent(new PopStateEvent('popstate')) }",
                    arg=route,
                )
            page.wait_for_function(
                "t => document.body.innerText.includes(t)", arg=text, timeout=15000
            )
            page.wait_for_timeout(400)
            dest = SHOTS / name
            page.screenshot(path=str(dest), full_page=True)
            manifest.append(
                {"file": name, "route": route, "bytes": dest.stat().st_size}
            )
            print(f"captured {name} ({dest.stat().st_size} bytes)")
        render_workbook(
            PROOF / "outputs" / "invoices.xlsx", SHOTS / "09_excel_output.png", browser
        )
        manifest.append(
            {
                "file": "09_excel_output.png",
                "source": "docs/proof/outputs/invoices.xlsx",
                "bytes": (SHOTS / "09_excel_output.png").stat().st_size,
            }
        )
        poppler = os.environ.get("POPPLER_PATH")
        if not poppler and os.name == "nt":
            candidate = Path(r"C:\poppler\Library\bin")
            poppler = str(candidate) if candidate.is_dir() else None
        pdf = convert_from_path(
            str(PROOF / "outputs" / "processing_report.pdf"),
            first_page=1,
            last_page=1,
            poppler_path=poppler,
            dpi=130,
        )[0]
        pdf.save(SHOTS / "10_pdf_report.png")
        manifest.append(
            {
                "file": "10_pdf_report.png",
                "source": "docs/proof/outputs/processing_report.pdf",
                "bytes": (SHOTS / "10_pdf_report.png").stat().st_size,
            }
        )
        browser.close()

    (LOGS / "screenshots.json").write_text(
        json.dumps(
            {
                "captured_at": datetime.now(UTC).isoformat(),
                "viewport": "1440x900",
                "files": manifest,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    server.should_exit = True
    thread.join(timeout=10)


if __name__ == "__main__":
    main()
