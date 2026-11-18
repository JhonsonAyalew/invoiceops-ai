from __future__ import annotations

import hmac
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

import httpx
from fastapi import APIRouter, Body, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.extraction.numbers import fmt_money
from app.extraction.ocr import SUPPORTED_LANGS, check_ocr
from app.extraction.pdf_text import inspect_pdf, sha256_file
from app.models import ALL_FIELDS, Correction, Document, DuplicateCandidate, ExportFile, Invoice, Job, LineItem
from app.services import exporter, processing, settings_store
from app.storage import StorageError, iter_zip_pdfs, safe_display_name

router = APIRouter(prefix="/api")
STATUSES = {"queued", "processing", "processed", "needs_review", "reviewed", "failed", "duplicate"}


# ---------------------------------------------------------------- deps
def ctx(request: Request):
    return request.app.state.ctx


def db(request: Request):
    with request.app.state.ctx.sf() as s:
        yield s


def auth(request: Request):
    tok = request.app.state.ctx.settings.admin_token
    if tok:
        given = request.headers.get("x-admin-token") or request.query_params.get("token") or ""
        if not hmac.compare_digest(given, tok):
            raise HTTPException(401, "Admin token required")


router.dependencies.append(Depends(auth))


def get_job(s: Session, job_id: str) -> Job:
    j = s.get(Job, job_id) if re.fullmatch(r"[0-9a-f]{32}", job_id) else None
    if not j:
        raise HTTPException(404, "Job not found")
    return j


def get_doc(s: Session, doc_id: str) -> Document:
    d = s.get(Document, doc_id)
    if not d:
        raise HTTPException(404, "Document not found")
    return d


def get_inv(s: Session, inv_id: str) -> Invoice:
    i = s.get(Invoice, inv_id)
    if not i:
        raise HTTPException(404, "Invoice not found")
    return i


def _str(v):
    if v is None:
        return None
    if isinstance(v, Decimal):
        return fmt_money(v)
    return v.isoformat() if isinstance(v, (date, datetime)) else str(v)


def effective_status(d: Document, i: Invoice | None) -> str:
    return "reviewed" if i is not None and i.reviewed else d.status


def doc_out(d: Document, i: Invoice | None = None) -> dict:
    out = {
        "id": d.id,
        "job_id": d.job_id,
        "name": d.original_name,
        "size_bytes": d.size_bytes,
        "pages": d.pages,
        "status": effective_status(d, i),
        "extraction_status": d.status,
        "error": d.error,
        "method": d.method,
        "duplicate_of": d.duplicate_of,
        "invoice_id": i.id if i else None,
    }
    if i:
        out.update(
            supplier_name=i.supplier_name,
            invoice_number=i.invoice_number,
            invoice_date=_str(i.invoice_date),
            currency=i.currency,
            total_amount=_str(i.total_amount),
            issue_count=sum(1 for x in (i.issues or []) if x["severity"] in ("warning", "error")),
        )
    return out


def job_counts(s: Session, job_id: str) -> dict:
    rows = s.execute(
        select(Document.status, Invoice.reviewed, func.count())
        .join(Invoice, Invoice.document_id == Document.id, isouter=True)
        .where(Document.job_id == job_id)
        .group_by(Document.status, Invoice.reviewed)
    ).all()
    c = {k: 0 for k in STATUSES}
    for st, rev, n in rows:
        c["reviewed" if rev else st] += n
    c["total"] = sum(c[k] for k in STATUSES)
    return c


def job_out(s: Session, j: Job) -> dict:
    return {
        "id": j.id,
        "name": j.name,
        "reference": j.reference,
        "client_note": j.client_note,
        "use_ai": j.use_ai,
        "ai_consent_provider": j.ai_consent_provider,
        "ai_consent_at": _str(j.ai_consent_at),
        "created_at": _str(j.created_at),
        "counts": job_counts(s, j.id),
    }


# ---------------------------------------------------------------- health / overview
@router.get("/health")
def health():
    return {"ok": True}


@router.get("/overview")
def overview(s: Session = Depends(db)):
    jobs = list(s.scalars(select(Job).order_by(Job.created_at.desc())))
    tot = {k: 0 for k in STATUSES}
    for j in jobs:
        for k, v in job_counts(s, j.id).items():
            if k in tot:
                tot[k] += v
    docs = sum(tot.values())
    return {"jobs": len(jobs), "documents": docs, "counts": tot, "recent_jobs": [job_out(s, j) for j in jobs[:6]]}


# ---------------------------------------------------------------- jobs
class JobIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    reference: str | None = Field(default=None, max_length=100)
    client_note: str | None = Field(default=None, max_length=2000)
    use_ai: bool = False


@router.post("/jobs", status_code=201)
def create_job(body: JobIn, request: Request, s: Session = Depends(db)):
    j = Job(name=body.name.strip(), reference=(body.reference or "").strip() or None, client_note=body.client_note, use_ai=body.use_ai)
    s.add(j)
    s.commit()
    request.app.state.ctx.storage.job_dir(j.id)
    return job_out(s, j)


@router.get("/jobs")
def list_jobs(s: Session = Depends(db)):
    return [job_out(s, j) for j in s.scalars(select(Job).order_by(Job.created_at.desc()))]


@router.get("/jobs/{job_id}")
def read_job(job_id: str, s: Session = Depends(db)):
    return job_out(s, get_job(s, job_id))


@router.delete("/jobs/{job_id}", status_code=204)
def remove_job(job_id: str, c=Depends(ctx), s: Session = Depends(db)):
    get_job(s, job_id)
    processing.delete_job(s, c.storage, job_id)


class ConsentIn(BaseModel):
    provider: str = Field(min_length=1, max_length=30)
    acknowledge: bool


@router.post("/jobs/{job_id}/consent")
def grant_consent(job_id: str, body: ConsentIn, s: Session = Depends(db)):
    j = get_job(s, job_id)
    if not body.acknowledge:
        raise HTTPException(422, "You must explicitly acknowledge that document content will be sent to the provider")
    j.ai_consent_provider, j.ai_consent_at, j.use_ai = body.provider, datetime.now(timezone.utc), True
    s.commit()
    return job_out(s, j)


@router.delete("/jobs/{job_id}/consent")
def revoke_consent(job_id: str, s: Session = Depends(db)):
    j = get_job(s, job_id)
    j.ai_consent_provider = j.ai_consent_at = None
    s.commit()
    return job_out(s, j)


@router.patch("/jobs/{job_id}")
def update_job(job_id: str, body: dict = Body(...), s: Session = Depends(db)):
    j = get_job(s, job_id)
    if "use_ai" in body:
        j.use_ai = bool(body["use_ai"])
    for k, n in (("name", 200), ("reference", 100), ("client_note", 2000)):
        if k in body and isinstance(body[k], (str, type(None))):
            if k == "name" and not (body[k] or "").strip():
                raise HTTPException(422, "name required")
            setattr(j, k, (body[k] or "").strip()[:n] or None if k != "name" else body[k].strip()[:n])
    s.commit()
    return job_out(s, j)


# ---------------------------------------------------------------- upload
def _ingest(s: Session, c, job: Job, name: str, stream, results: list) -> None:
    def add(**kw):
        d = Document(job_id=job.id, original_name=name, **kw)
        s.add(d)
        s.flush()
        results.append(d)
        return d

    try:
        stored, size = c.storage.save_stream(job.id, stream, c.settings.max_upload_mb * 1024 * 1024)
    except StorageError as e:
        add(status="failed", error=e.code)
        return
    path = c.storage.doc_path(job.id, stored)
    sha = sha256_file(path)
    info = inspect_pdf(path)
    prior = s.scalar(
        select(Document)
        .where(Document.job_id == job.id, Document.sha256 == sha, Document.stored_name.is_not(None))
        .order_by(Document.created_at)
    )
    if prior is not None:
        path.unlink(missing_ok=True)
        add(status="duplicate", sha256=sha, size_bytes=size, duplicate_of=prior.id, error="identical file already in this job")
        return
    if not info.ok:
        add(status="failed", stored_name=stored, sha256=sha, size_bytes=size, error=info.error)
        return
    add(status="queued", stored_name=stored, sha256=sha, size_bytes=size, pages=info.pages)


@router.post("/jobs/{job_id}/upload", status_code=201)
def upload(job_id: str, files: list[UploadFile] = File(...), c=Depends(ctx), s: Session = Depends(db)):
    job = get_job(s, job_id)
    created: list[Document] = []
    mb = 1024 * 1024
    for f in files:
        name = safe_display_name(f.filename)
        head = f.file.read(4)
        f.file.seek(0)
        if head.startswith(b"PK\x03\x04") or name.lower().endswith(".zip"):
            try:
                for inner, fh, err in iter_zip_pdfs(
                    f.file, c.settings.max_zip_files, c.settings.max_zip_uncompressed_mb * mb, c.settings.max_upload_mb * mb
                ):
                    if fh is None:
                        s.add(Document(job_id=job.id, original_name=inner, status="failed", error=err))
                        continue
                    with fh:
                        _ingest(s, c, job, inner, fh, created)
            except StorageError as e:
                s.add(Document(job_id=job.id, original_name=name, status="failed", error=e.code))
        elif head == b"%PDF":
            _ingest(s, c, job, name, f.file, created)
        else:
            s.add(Document(job_id=job.id, original_name=name, status="failed", error="unsupported_file_type"))
        s.commit()
    return {"job": job_out(s, job), "added": len(created)}


@router.post("/jobs/{job_id}/process")
def process(job_id: str, c=Depends(ctx), s: Session = Depends(db)):
    job = get_job(s, job_id)
    ids = list(s.scalars(select(Document.id).where(Document.job_id == job.id, Document.status == "queued")))
    if not ids:
        raise HTTPException(409, "No queued documents to process")
    c.processor.enqueue(ids)
    return {"queued": len(ids)}


@router.post("/documents/{doc_id}/retry")
def retry(doc_id: str, c=Depends(ctx), s: Session = Depends(db)):
    d = get_doc(s, doc_id)
    if not d.stored_name:
        raise HTTPException(409, "No stored file for this document; upload it again")
    if d.status == "processing":
        raise HTTPException(409, "Already processing")
    d.status, d.error = "queued", None
    s.commit()
    c.processor.enqueue([d.id])
    return {"queued": 1}


@router.get("/jobs/{job_id}/progress")
def progress(job_id: str, s: Session = Depends(db)):
    cnt = job_counts(s, get_job(s, job_id).id)
    active = cnt["queued"] + cnt["processing"]
    finished = cnt["total"] - active
    return {"counts": cnt, "active": active > 0, "percent": 100 if not cnt["total"] else int(100 * finished / cnt["total"])}


# ---------------------------------------------------------------- documents / invoices
@router.get("/jobs/{job_id}/documents")
def list_documents(job_id: str, status: str | None = None, s: Session = Depends(db)):
    get_job(s, job_id)
    if status and status not in STATUSES:
        raise HTTPException(422, "unknown status")
    rows = s.execute(
        select(Document, Invoice)
        .join(Invoice, Invoice.document_id == Document.id, isouter=True)
        .where(Document.job_id == job_id)
        .order_by(Document.created_at, Document.original_name)
    ).all()
    out = [doc_out(d, i) for d, i in rows]
    return [d for d in out if not status or d["status"] == status]


@router.get("/documents/{doc_id}/file")
def document_file(doc_id: str, c=Depends(ctx), s: Session = Depends(db)):
    d = get_doc(s, doc_id)
    if not d.stored_name:
        raise HTTPException(404, "No stored file")
    p = c.storage.doc_path(d.job_id, d.stored_name)
    if not p.exists():
        raise HTTPException(404, "File missing")
    return FileResponse(p, media_type="application/pdf", headers={"Content-Disposition": "inline", "X-Content-Type-Options": "nosniff"})


@router.get("/invoices/{inv_id}")
def read_invoice(inv_id: str, s: Session = Depends(db)):
    i = get_inv(s, inv_id)
    d = s.get(Document, i.document_id)
    items = s.scalars(select(LineItem).where(LineItem.invoice_id == i.id).order_by(LineItem.position)).all()
    return {
        "id": i.id,
        "job_id": i.job_id,
        "document": doc_out(d, i),
        "fields": {f: _str(getattr(i, f)) for f in ALL_FIELDS},
        "original": i.original,
        "meta": i.meta,
        "issues": i.issues,
        "ai": i.ai,
        "edited_fields": i.edited_fields,
        "reviewed": i.reviewed,
        "reviewed_at": _str(i.reviewed_at),
        "extraction_method": i.extraction_method,
        "source_page": i.source_page,
        "line_items": [
            {
                "description": x.description,
                "quantity": _str(x.quantity),
                "unit": x.unit,
                "unit_price": _str(x.unit_price),
                "discount": _str(x.discount),
                "tax_rate": _str(x.tax_rate),
                "tax_amount": _str(x.tax_amount),
                "line_total": _str(x.line_total),
                "reliable": x.reliable,
                "note": x.note,
            }
            for x in items
        ],
    }


@router.patch("/invoices/{inv_id}")
def correct_invoice(inv_id: str, body: dict = Body(...), s: Session = Depends(db)):
    i = get_inv(s, inv_id)
    try:
        changed = processing.apply_corrections(s, i, body)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {"changed": changed, **read_invoice(inv_id, s)}


@router.put("/invoices/{inv_id}/line-items")
def put_line_items(inv_id: str, body: list[dict] = Body(...), s: Session = Depends(db)):
    i = get_inv(s, inv_id)
    try:
        processing.replace_line_items(s, i, body)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return read_invoice(inv_id, s)


class ReviewIn(BaseModel):
    reviewed: bool = True


@router.post("/invoices/{inv_id}/review")
def review(inv_id: str, body: ReviewIn, s: Session = Depends(db)):
    i = get_inv(s, inv_id)
    i.reviewed = body.reviewed
    i.reviewed_at = datetime.now(timezone.utc) if body.reviewed else None
    s.commit()
    return read_invoice(inv_id, s)


@router.get("/invoices/{inv_id}/corrections")
def corrections(inv_id: str, s: Session = Depends(db)):
    get_inv(s, inv_id)
    return [
        {"field": x.field, "old": x.old_value, "new": x.new_value, "at": _str(x.at)}
        for x in s.scalars(select(Correction).where(Correction.invoice_id == inv_id).order_by(Correction.id))
    ]


@router.get("/jobs/{job_id}/duplicates")
def duplicates(job_id: str, s: Session = Depends(db)):
    get_job(s, job_id)
    names = dict(s.execute(select(Document.id, Document.original_name).where(Document.job_id == job_id)).all())
    return [
        {"a": names.get(x.doc_a), "b": names.get(x.doc_b), "doc_a": x.doc_a, "doc_b": x.doc_b, "kind": x.kind, "score": x.score}
        for x in s.scalars(select(DuplicateCandidate).where(DuplicateCandidate.job_id == job_id))
    ]


# ---------------------------------------------------------------- exports
class ExportIn(BaseModel):
    kinds: list[Literal["xlsx", "csv_invoices", "csv_line_items", "pdf_report"]] = Field(min_length=1)


def _slug(t: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-")[:40] or "job"


@router.post("/jobs/{job_id}/exports", status_code=201)
def create_exports(job_id: str, body: ExportIn, c=Depends(ctx), s: Session = Depends(db)):
    job = get_job(s, job_id)
    data = exporter.JobData(s, job.id)
    out = []
    for kind in dict.fromkeys(body.kinds):
        ext, fn, label = exporter.KINDS[kind]
        blob = fn(data)
        import uuid

        stored = f"{uuid.uuid4().hex}.{ext}"
        c.storage.export_path(job.id, stored).write_bytes(blob)
        fname = f"{_slug(job.reference or job.name)}_{label}_{date.today():%Y%m%d}.{ext}"
        e = ExportFile(job_id=job.id, kind=kind, filename=fname, stored_name=stored, size_bytes=len(blob))
        s.add(e)
        s.commit()
        out.append(export_out(e))
    return out


def export_out(e: ExportFile) -> dict:
    return {
        "id": e.id,
        "job_id": e.job_id,
        "kind": e.kind,
        "filename": e.filename,
        "size_bytes": e.size_bytes,
        "created_at": _str(e.created_at),
    }


@router.get("/jobs/{job_id}/exports")
def list_exports(job_id: str, s: Session = Depends(db)):
    get_job(s, job_id)
    return [export_out(e) for e in s.scalars(select(ExportFile).where(ExportFile.job_id == job_id).order_by(ExportFile.created_at.desc()))]


@router.get("/exports/{export_id}/download")
def download_export(export_id: str, c=Depends(ctx), s: Session = Depends(db)):
    e = s.get(ExportFile, export_id)
    if not e:
        raise HTTPException(404, "Export not found")
    p = c.storage.export_path(e.job_id, e.stored_name)
    if not p.exists():
        raise HTTPException(404, "Export file missing")
    mt = {
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv; charset=utf-8",
        "pdf": "application/pdf",
    }[e.stored_name.rsplit(".", 1)[1]]
    return FileResponse(p, media_type=mt, filename=e.filename)


# ---------------------------------------------------------------- settings
def _settings_view(s: Session, c) -> dict:
    ocr, ai = settings_store.load_ocr(s), settings_store.load_ai(s)
    st = check_ocr(ocr)
    st_ = c.settings
    return {
        "app": {
            "retention_days": st_.retention_days,
            "max_upload_mb": st_.max_upload_mb,
            "workers": st_.workers,
            "auth_enabled": bool(st_.admin_token),
            "max_zip_files": st_.max_zip_files,
        },
        "ocr": {
            "languages": list(ocr.languages),
            "model_dir": ocr.model_dir,
            "device": ocr.device,
            "poppler_path": ocr.poppler_path,
            "timeout_seconds": ocr.timeout_seconds,
            "dpi": ocr.dpi,
            "supported_languages": SUPPORTED_LANGS,
        },
        "ocr_status": {
            "ready": st.ready,
            "package_found": st.package_found,
            "version": st.version,
            "model": st.model,
            "det_model_found": st.det_model_found,
            "rec_model_found": st.rec_model_found,
            "model_dir": st.model_dir,
            "device": st.device,
            "languages": st.languages,
            "poppler_found": st.poppler_found,
            "poppler_path": st.poppler_path,
            "problems": st.problems,
        },
        "ai": {
            "provider": ai.provider,
            "is_cloud": ai.provider == "groq",
            "ollama_url": ai.ollama_url,
            "ollama_model": ai.ollama_model,
            "groq_base_url": ai.groq_base_url,
            "groq_model": ai.groq_model,
            "groq_key_configured": bool(ai.groq_api_key),
        },
    }


@router.get("/settings")
def get_settings(c=Depends(ctx), s: Session = Depends(db)):
    return _settings_view(s, c)


@router.put("/settings/ocr")
def put_ocr(body: dict = Body(...), c=Depends(ctx), s: Session = Depends(db)):
    try:
        settings_store.save_ocr(s, body)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return _settings_view(s, c)


@router.put("/settings/ai")
def put_ai(body: dict = Body(...), c=Depends(ctx), s: Session = Depends(db)):
    try:
        settings_store.save_ai(s, body)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return _settings_view(s, c)


@router.post("/settings/ai/test")
def test_ai(s: Session = Depends(db)):
    """Connectivity check that never sends document content."""
    ai = settings_store.load_ai(s)
    if ai.provider == "none":
        return {"ok": True, "message": "AI disabled. Extraction uses rules and OCR only."}
    if ai.provider == "ollama":
        try:
            r = httpx.get(f"{ai.ollama_url.rstrip('/')}/api/tags", timeout=5, trust_env=False)
            names = [m.get("name") for m in r.json().get("models", [])]
            ok = ai.ollama_model in names
            return {
                "ok": ok,
                "message": f"Ollama reachable. Model {ai.ollama_model} {'is' if ok else 'is NOT'} installed (run: ollama pull {ai.ollama_model}).",
            }
        except (httpx.HTTPError, ValueError):
            return {"ok": False, "message": "Cannot reach Ollama. Is it running at " + ai.ollama_url + "?"}
    if ai.provider == "groq":
        if not ai.groq_api_key:
            return {"ok": False, "message": "GROQ_API_KEY is not configured. Set it in .env and restart."}
        try:
            r = httpx.get(
                f"{ai.groq_base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {ai.groq_api_key}"},
                timeout=10,
            )
            if r.status_code in (401, 403):
                return {"ok": False, "message": "Groq authentication failed. Check GROQ_API_KEY."}
            r.raise_for_status()
            names = [m.get("id") for m in r.json().get("data", []) if isinstance(m, dict)]
            ok = ai.groq_model in names
            return {
                "ok": ok,
                "message": f"Groq reachable. Model {ai.groq_model} {'is' if ok else 'is NOT'} available for this key.",
            }
        except (httpx.HTTPError, ValueError):
            return {"ok": False, "message": "Cannot reach Groq. Check the network/proxy and GROQ_BASE_URL."}
    return {"ok": False, "message": f"Unknown AI provider '{ai.provider}' (use none, ollama or groq)."}


@router.post("/maintenance/purge")
def purge(c=Depends(ctx), s: Session = Depends(db)):
    return {"deleted_jobs": processing.purge_expired(s, c.storage, c.settings.retention_days)}
