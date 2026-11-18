"""Hybrid pipeline: inspect -> native text -> OCR only where needed -> parse -> validate."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.config import OcrSettings

from . import ocr as ocr_mod
from .parser import ParsedInvoice, parse_invoice
from .pdf_text import extract_native_pages, inspect_pdf, sha256_file
from .validation import validate


@dataclass
class ExtractionResult:
    filename: str
    sha256: str
    status: str  # processed | needs_review | failed
    pages: int = 0
    method: str = "none"  # native | ocr | native+ocr
    error: str | None = None
    parsed: ParsedInvoice | None = None
    issues: list[dict] = field(default_factory=list)
    ocr_pages: list[int] = field(default_factory=list)
    text_pages: list[str] = field(default_factory=list)
    ai: dict | None = None  # AI audit record (provider, filled, rejected) or None


def extract_document(path: str | Path, settings: OcrSettings | None = None) -> ExtractionResult:
    settings = settings or OcrSettings.from_env()
    p = Path(path)
    sha = sha256_file(p) if p.exists() else ""
    info = inspect_pdf(p)
    if not info.ok:
        return ExtractionResult(p.name, sha, "failed", error=info.error)
    res = ExtractionResult(p.name, sha, "processed", pages=info.pages)
    try:
        texts = extract_native_pages(p)
    except Exception as e:  # noqa: BLE001 - any parser failure marks the document failed, not the batch
        return ExtractionResult(p.name, sha, "failed", pages=info.pages, error=f"native_extraction_failed: {type(e).__name__}")
    need = [i + 1 for i, t in enumerate(texts) if len(t.strip()) < settings.min_native_chars_per_page]
    if need:
        try:
            for n, t in ocr_mod.ocr_pdf_pages(p, settings, need).items():
                texts[n - 1] = t
            res.ocr_pages = need
        except ocr_mod.OcrError as e:
            if len(need) == len(texts):
                return ExtractionResult(p.name, sha, "failed", pages=info.pages, error=f"ocr_failed: {e}")
            res.issues.append({"code": "ocr_partial", "severity": "warning", "message": str(e), "field": None})
    res.method = "native" if not res.ocr_pages else ("ocr" if len(res.ocr_pages) == len(texts) else "native+ocr")
    res.text_pages = texts
    res.parsed = parse_invoice(texts)
    res.issues += validate(res.parsed)
    if res.method != "native":
        res.issues.append(
            {"code": "ocr_used", "severity": "info", "message": "OCR text used; verify values against the PDF", "field": None}
        )
    res.status = "needs_review" if any(i["severity"] in ("warning", "error") for i in res.issues) else "processed"
    return res
