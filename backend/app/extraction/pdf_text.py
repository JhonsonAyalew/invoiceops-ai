"""Native PDF text extraction (pdfplumber/pypdf) and file inspection. No PyMuPDF."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
from pypdf import PdfReader
from pypdf.errors import PdfReadError


@dataclass
class PdfInfo:
    ok: bool
    pages: int = 0
    encrypted: bool = False
    error: str | None = None


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def inspect_pdf(path: str | Path) -> PdfInfo:
    """Detect corrupted / encrypted / non-PDF files before processing."""
    p = Path(path)
    try:
        with open(p, "rb") as f:
            if f.read(5) != b"%PDF-":
                return PdfInfo(False, error="not_a_pdf")
        r = PdfReader(str(p))
        if r.is_encrypted:
            try:
                if r.decrypt("") == 0:
                    return PdfInfo(False, encrypted=True, error="encrypted")
            except Exception:
                return PdfInfo(False, encrypted=True, error="encrypted")
        return PdfInfo(True, pages=len(r.pages))
    except (PdfReadError, ValueError, OSError, KeyError) as e:
        return PdfInfo(False, error=f"corrupted: {type(e).__name__}")


def extract_native_pages(path: str | Path) -> list[str]:
    """Return text per page ('' where the page has no text layer).

    pypdf's layout mode keeps table columns aligned, which makes line-item parsing
    far more reliable than flat text. pdfplumber is only used as a fallback.
    """
    p = Path(path)
    out: list[str] = []
    failed: list[int] = []
    try:
        reader = PdfReader(str(p))
        for i, page in enumerate(reader.pages):
            try:
                out.append(page.extract_text(extraction_mode="layout") or "")
            except Exception:
                out.append("")
                failed.append(i)
    except Exception:
        with pdfplumber.open(str(p)) as pdf:
            return [page.extract_text(layout=True) or "" for page in pdf.pages]
    if failed:
        try:
            with pdfplumber.open(str(p)) as pdf:
                for i in failed:
                    if i < len(pdf.pages):
                        out[i] = pdf.pages[i].extract_text(layout=True) or ""
        except Exception:
            pass
    return out
