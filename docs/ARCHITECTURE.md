# Architecture

Modular monolith: one FastAPI process, one PostgreSQL database, a thread pool for background extraction, and a React single-page app
served by the same process. No queues or microservices.

```
backend/app/
  extraction/   numbers.py (Decimal + locale parsing) · pdf_text.py (pypdf/pdfplumber, SHA-256) · ocr.py (PaddleOCR PP-OCRv6 Medium,
                Poppler rendering, cached engine, timeout) · parser.py (fields, line items) · validation.py · duplicates.py · pipeline.py
  ai/           base.py (provider interface) · providers.py (Ollama, Groq) · consent.py · grounding.py · enrich.py
  services/     processing.py (queue, persistence, corrections, delete, retention) · exporter.py (xlsx/csv/pdf) · settings_store.py
  api.py        REST routes            storage.py   per-job file storage, safe ZIP reading
  models.py     SQLAlchemy tables      db.py        NUMERIC money type
frontend/src/   pages (Overview, Jobs, NewJob, JobPages, Review, ExportCenter, SettingsPages) · api.ts · ui.tsx
backend/migrations/   Alembic
```

## Extraction flow
`inspect (magic bytes, encryption, corruption)` → `native text per page` → `OCR only for pages with no usable text` → `rule-based parse`
→ `validate` → *(optional)* `AI enrichment` → `validate again` → store (original values preserved separately from corrected values).

## Key decisions
- **Money**: `Decimal` in Python, `NUMERIC(20,4)` in PostgreSQL. No floats anywhere, including JSON from AI (parsed with `parse_float=Decimal`).
  Missing is `NULL`; a tax of `0` is stored as a real zero.
- **AI safety**: provider-independent interface; Ollama runs locally, while Groq is cloud-only and requires explicit per-job
  consent before any document text is sent; every AI value must be grounded in the document text; AI never overwrites confident
  rule values; document text is fenced as untrusted data.
- **Isolation**: every document, invoice and export belongs to one job; files live in `data/jobs/<job_id>/` under random names; client file
  names are display-only; there is no static file serving - PDFs are served by an API route.
- **Auditability**: `invoices.original` (never modified), per-field `meta` (confidence, source, evidence), `corrections` table, `edited_fields`.
- **Exports**: generated from database rows of the selected job only; spreadsheet text starting with `= + - @` is neutralised.

## Security notes
Server binds to 127.0.0.1. Optional `ADMIN_TOKEN`. ZIP entries are never used as paths; entry-count and size limits apply. No secrets are
returned by the API or logged. Retention (`RETENTION_DAYS`) purges old jobs at startup and via `POST /api/maintenance/purge`.
