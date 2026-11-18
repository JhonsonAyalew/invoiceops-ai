from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.base import AIError
from app.ai.consent import CloudConsent
from app.ai.enrich import ai_enrich
from app.ai.providers import get_provider
from app.config import AppSettings
from app.extraction.duplicates import find_duplicates
from app.extraction.numbers import parse_amount
from app.extraction.parser import FieldValue, ParsedInvoice
from app.extraction.parser import LineItem as PLineItem
from app.extraction.pipeline import ExtractionResult, extract_document
from app.extraction.validation import validate
from app.models import ALL_FIELDS, DATE_FIELDS, MONEY_FIELDS, Correction, Document, DuplicateCandidate, ExportFile, Invoice, Job, LineItem
from app.storage import Storage

from . import settings_store

_lock = threading.Lock()


def _now():
    return datetime.now(timezone.utc)


def _s(v):
    if v is None:
        return None
    if isinstance(v, Decimal):
        from app.extraction.numbers import fmt_money

        return fmt_money(v)
    return v.isoformat() if isinstance(v, date) else str(v)


class Processor:
    def __init__(self, settings: AppSettings, sf: sessionmaker, storage: Storage):
        self.settings, self.sf, self.storage = settings, sf, storage
        self.pool = ThreadPoolExecutor(max_workers=settings.workers, thread_name_prefix="invoiceops")

    # ---- queueing ----
    def enqueue(self, doc_ids: list[str]) -> None:
        for d in doc_ids:
            if self.settings.sync_processing:
                self.process_document(d)
            else:
                self.pool.submit(self.process_document, d)

    def process_document(self, doc_id: str) -> None:
        with self.sf() as s:
            doc = s.get(Document, doc_id)
            if not doc:
                return
            job = s.get(Job, doc.job_id)
            doc.status, doc.error = "processing", None
            s.commit()
            try:
                res = self._extract(s, job, doc)
                self._persist(s, job, doc, res)
            except Exception as e:  # noqa: BLE001 - one bad document must never stop the batch
                s.rollback()
                doc = s.get(Document, doc_id)
                doc.status, doc.error, doc.processed_at = "failed", f"internal_error: {type(e).__name__}", _now()
                s.commit()
            self._maybe_finalize(s, doc.job_id)

    def _extract(self, s: Session, job: Job, doc: Document) -> ExtractionResult:
        path = self.storage.doc_path(job.id, doc.stored_name)
        res = extract_document(path, settings_store.load_ocr(s))
        if res.status == "failed" or not job.use_ai or res.parsed is None:
            return res
        ai_settings = settings_store.load_ai(s)
        try:
            provider = get_provider(ai_settings)
        except AIError as e:
            res.issues.append({"code": "ai_failed", "severity": "info", "field": None, "message": f"AI not available: {e}"})
            return res
        if provider is None:
            return res
        consent = None
        if job.ai_consent_provider:
            consent = CloudConsent(job.id, job.ai_consent_provider, job.ai_consent_at or _now())
        if provider.is_cloud and not (consent and consent.provider == provider.name):
            res.issues.append(
                {
                    "code": "ai_skipped_no_consent",
                    "severity": "info",
                    "field": None,
                    "message": f"Cloud AI ({provider.name}) skipped: no operator consent recorded for this job",
                }
            )
            return res
        return ai_enrich(res, provider, job.id, consent, ai_settings, force=True)

    def _persist(self, s: Session, job: Job, doc: Document, res: ExtractionResult) -> None:
        old = s.scalar(select(Invoice).where(Invoice.document_id == doc.id))
        if old:
            s.execute(delete(LineItem).where(LineItem.invoice_id == old.id))
            s.execute(delete(Correction).where(Correction.invoice_id == old.id))
            s.delete(old)
            s.flush()
        doc.sha256, doc.pages, doc.method = res.sha256 or doc.sha256, res.pages or doc.pages, res.method
        doc.status, doc.error, doc.processed_at = res.status, res.error, _now()
        if res.parsed is not None:
            p = res.parsed
            inv = Invoice(job_id=job.id, document_id=doc.id, extraction_method=res.method, issues=res.issues, ai=res.ai)
            orig, meta = {}, {}
            for f in ALL_FIELDS:
                v = p.get(f)
                setattr(inv, f, v)
                orig[f] = _s(v)
                if f in p.fields:
                    fv = p.fields[f]
                    meta[f] = {"confidence": fv.confidence, "source": fv.source, "evidence": fv.evidence[:200], "page": fv.page}
            inv.original, inv.meta = orig, meta
            inv.source_page = next((p.fields[f].page for f in ("total_amount", "invoice_number") if f in p.fields and p.fields[f].page), 1)
            s.add(inv)
            s.flush()
            for i, it in enumerate(p.line_items):
                s.add(
                    LineItem(
                        invoice_id=inv.id,
                        position=i,
                        description=it.description,
                        quantity=it.quantity,
                        unit=it.unit,
                        unit_price=it.unit_price,
                        discount=it.discount,
                        tax_rate=it.tax_rate,
                        tax_amount=it.tax_amount,
                        line_total=it.line_total,
                        reliable=it.reliable,
                        note=it.note,
                        page=it.page,
                    )
                )
        s.commit()

    def _maybe_finalize(self, s: Session, job_id: str) -> None:
        with _lock:
            pending = s.scalar(
                select(func.count()).select_from(Document).where(Document.job_id == job_id, Document.status.in_(("queued", "processing")))
            )
            if not pending:
                detect_duplicates(s, job_id)


def detect_duplicates(s: Session, job_id: str) -> int:
    """Recompute duplicate candidates for a job (file hash + invoice-level + similarity)."""
    s.execute(delete(DuplicateCandidate).where(DuplicateCandidate.job_id == job_id))
    rows = s.execute(
        select(Document, Invoice)
        .join(Invoice, Invoice.document_id == Document.id, isouter=True)
        .where(Document.job_id == job_id, Document.status != "failed")
    ).all()
    recs = [
        {
            "id": d.id,
            "sha256": d.sha256,
            "supplier_name": i.supplier_name if i else None,
            "invoice_number": i.invoice_number if i else None,
            "total_amount": i.total_amount if i else None,
            "invoice_date": i.invoice_date if i else None,
        }
        for d, i in rows
    ]
    found = find_duplicates(recs)
    for f in found:
        s.add(DuplicateCandidate(job_id=job_id, doc_a=f["a"], doc_b=f["b"], kind=f["kind"], score=float(f["score"])))
    s.commit()
    return len(found)


# ---------- manual corrections ----------
def parse_field_value(field: str, raw):
    """Validate a manually entered value. Returns the typed value (None for blank). Raises ValueError."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    if field in MONEY_FIELDS:
        v = parse_amount(str(raw))
        if v is None:
            raise ValueError(f"{field}: not a valid amount")
        return v
    if field in DATE_FIELDS:
        try:
            return date.fromisoformat(str(raw).strip())
        except ValueError as e:
            raise ValueError(f"{field}: use YYYY-MM-DD") from e
    v = str(raw).strip()
    if field == "currency":
        v = v.upper()
        if len(v) != 3 or not v.isalpha():
            raise ValueError("currency must be a 3-letter code")
    return v


def revalidate(s: Session, inv: Invoice) -> None:
    items = s.scalars(select(LineItem).where(LineItem.invoice_id == inv.id).order_by(LineItem.position)).all()
    p = ParsedInvoice()
    for f in ALL_FIELDS:
        if getattr(inv, f) is not None:
            p.fields[f] = FieldValue(getattr(inv, f))
    p.line_items = [
        PLineItem(i.description, i.quantity, i.unit, i.unit_price, i.discount, i.tax_rate, i.tax_amount, i.line_total, i.reliable, i.note)
        for i in items
    ]
    keep = [
        x
        for x in (inv.issues or [])
        if x["code"]
        in ("ocr_used", "ocr_partial", "ai_used", "ai_checked", "ai_disagreement", "ai_rejected", "ai_failed", "ai_skipped_no_consent")
    ]
    inv.issues = validate(p) + keep


def apply_corrections(s: Session, inv: Invoice, changes: dict) -> list[str]:
    unknown = [k for k in changes if k not in ALL_FIELDS]
    if unknown:
        raise ValueError(f"unknown field(s): {', '.join(unknown)}")
    parsed = {k: parse_field_value(k, v) for k, v in changes.items()}  # validate everything first
    edited = list(inv.edited_fields or [])
    changed = []
    for k, new in parsed.items():
        old = getattr(inv, k)
        if old == new:
            continue
        s.add(Correction(invoice_id=inv.id, field=k, old_value=_s(old), new_value=_s(new)))
        setattr(inv, k, new)
        if k not in edited:
            edited.append(k)
        changed.append(k)
    inv.edited_fields = edited
    if changed:
        revalidate(s, inv)
    s.commit()
    return changed


def _line_money(it: dict, key: str, n: int):
    v = it.get(key)
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    d = parse_amount(str(v))
    if d is None:
        raise ValueError(f"line {n + 1}: invalid {key}")
    return d


def replace_line_items(s: Session, inv: Invoice, items: list[dict]) -> None:
    from app.extraction.parser import CENT

    new = []
    for n, it in enumerate(items):
        desc = (it.get("description") or "").strip()
        if not desc:
            raise ValueError(f"line {n + 1}: description required")
        q, u, t = (_line_money(it, k, n) for k in ("quantity", "unit_price", "line_total"))
        reliable = not (q is not None and u is not None and t is not None and abs((q * u).quantize(CENT) - t) > CENT)
        new.append(
            LineItem(
                invoice_id=inv.id,
                position=n,
                description=desc,
                quantity=q,
                unit=(it.get("unit") or None),
                unit_price=u,
                discount=_line_money(it, "discount", n),
                tax_rate=_line_money(it, "tax_rate", n),
                tax_amount=_line_money(it, "tax_amount", n),
                line_total=t,
                reliable=reliable,
                note=None if reliable else "qty x unit price differs from line total",
            )
        )
    s.execute(delete(LineItem).where(LineItem.invoice_id == inv.id))
    s.add_all(new)
    s.flush()
    ed = list(inv.edited_fields or [])
    if "line_items" not in ed:
        ed.append("line_items")
    inv.edited_fields = ed
    revalidate(s, inv)
    s.commit()


# ---------- deletion & retention ----------
def delete_job(s: Session, storage: Storage, job_id: str) -> None:
    inv_ids = select(Invoice.id).where(Invoice.job_id == job_id)
    s.execute(delete(Correction).where(Correction.invoice_id.in_(inv_ids)))
    s.execute(delete(LineItem).where(LineItem.invoice_id.in_(inv_ids)))
    for model in (Invoice, DuplicateCandidate, ExportFile, Document):
        s.execute(delete(model).where(model.job_id == job_id))
    s.execute(delete(Job).where(Job.id == job_id))
    s.commit()
    storage.delete_job(job_id)


def purge_expired(s: Session, storage: Storage, retention_days: int) -> list[str]:
    if retention_days <= 0:
        return []
    cutoff = _now() - timedelta(days=retention_days)
    ids = list(s.scalars(select(Job.id).where(Job.created_at < cutoff)))
    for j in ids:
        delete_job(s, storage, j)
    return ids
