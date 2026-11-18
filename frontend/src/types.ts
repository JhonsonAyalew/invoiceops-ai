export type Status =
  'queued' | 'processing' | 'processed' | 'needs_review' | 'reviewed' | 'failed' | 'duplicate'
export const STATUSES: Status[] = [
  'queued',
  'processing',
  'processed',
  'needs_review',
  'reviewed',
  'failed',
  'duplicate',
]
export type Counts = Record<Status, number> & { total: number }

export interface Job {
  id: string
  name: string
  reference: string | null
  client_note: string | null
  use_ai: boolean
  ai_consent_provider: string | null
  ai_consent_at: string | null
  created_at: string
  counts: Counts
}
export interface Doc {
  id: string
  job_id: string
  name: string
  size_bytes: number
  pages: number
  status: Status
  extraction_status: string
  error: string | null
  method: string | null
  duplicate_of: string | null
  invoice_id: string | null
  supplier_name?: string | null
  invoice_number?: string | null
  invoice_date?: string | null
  currency?: string | null
  total_amount?: string | null
  issue_count?: number
}
export interface Issue {
  code: string
  severity: 'info' | 'warning' | 'error'
  message: string
  field: string | null
}
export interface FieldMeta {
  confidence: number
  source: string
  evidence: string
}
export interface LineItem {
  description: string
  quantity: string | null
  unit: string | null
  unit_price: string | null
  discount: string | null
  tax_rate: string | null
  tax_amount: string | null
  line_total: string | null
  reliable: boolean
  note: string | null
}
export interface Invoice {
  id: string
  job_id: string
  document: Doc
  fields: Record<string, string | null>
  original: Record<string, string | null>
  meta: Record<string, FieldMeta>
  issues: Issue[]
  edited_fields: string[]
  reviewed: boolean
  reviewed_at: string | null
  extraction_method: string
  source_page: number | null
  line_items: LineItem[]
}
export interface ExportRow {
  id: string
  job_id: string
  kind: string
  filename: string
  size_bytes: number
  created_at: string
}
export interface Progress {
  counts: Counts
  active: boolean
  percent: number
}
export interface Overview {
  jobs: number
  documents: number
  counts: Record<Status, number>
  recent_jobs: Job[]
}
export interface DuplicateRow {
  a: string
  b: string
  doc_a: string
  doc_b: string
  kind: string
  score: number
}
export interface Settings {
  app: {
    retention_days: number
    max_upload_mb: number
    workers: number
    auth_enabled: boolean
    max_zip_files: number
  }
  ocr: {
    languages: string[]
    model_dir: string | null
    device: string
    poppler_path: string | null
    timeout_seconds: number
    dpi: number
    supported_languages: Record<string, string>
  }
  ocr_status: {
    ready: boolean
    package_found: boolean
    version: string | null
    model: string
    det_model_found: boolean
    rec_model_found: boolean
    model_dir: string | null
    device: string
    languages: string[]
    poppler_found: boolean
    poppler_path: string | null
    problems: string[]
  }
  ai: {
    provider: string
    is_cloud: boolean
    ollama_url: string
    ollama_model: string
    groq_base_url: string
    groq_model: string
    groq_key_configured: boolean
  }
}
