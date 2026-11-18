import type { DuplicateRow, Doc, ExportRow, Invoice, Job, Overview, Progress, Settings } from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export const getToken = () => localStorage.getItem('adminToken') ?? ''
export const setToken = (t: string) => localStorage.setItem('adminToken', t)
const tokenQuery = () => (getToken() ? `?token=${encodeURIComponent(getToken())}` : '')

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (getToken()) headers.set('X-Admin-Token', getToken())
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const r = await fetch('/api' + path, { ...init, headers })
  if (r.status === 401) {
    window.dispatchEvent(new Event('auth-required'))
    throw new ApiError(401, 'Admin token required')
  }
  if (!r.ok) {
    let msg = r.statusText
    try {
      const j = await r.json()
      msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch {
      /* keep status text */
    }
    throw new ApiError(r.status, msg)
  }
  return r.status === 204 ? (undefined as T) : ((await r.json()) as T)
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
})

export const api = {
  overview: () => req<Overview>('/overview'),
  jobs: () => req<Job[]>('/jobs'),
  job: (id: string) => req<Job>(`/jobs/${id}`),
  createJob: (b: { name: string; reference?: string; client_note?: string; use_ai: boolean }) =>
    req<Job>('/jobs', json('POST', b)),
  deleteJob: (id: string) => req<void>(`/jobs/${id}`, { method: 'DELETE' }),
  consent: (id: string, provider: string) =>
    req<Job>(`/jobs/${id}/consent`, json('POST', { provider, acknowledge: true })),
  revokeConsent: (id: string) => req<Job>(`/jobs/${id}/consent`, { method: 'DELETE' }),
  upload: (id: string, files: File[]) => {
    const fd = new FormData()
    files.forEach((f) => fd.append('files', f, f.name))
    return req<{ job: Job; added: number }>(`/jobs/${id}/upload`, { method: 'POST', body: fd })
  },
  process: (id: string) => req<{ queued: number }>(`/jobs/${id}/process`, { method: 'POST' }),
  retry: (docId: string) => req<{ queued: number }>(`/documents/${docId}/retry`, { method: 'POST' }),
  progress: (id: string) => req<Progress>(`/jobs/${id}/progress`),
  documents: (id: string, status?: string) =>
    req<Doc[]>(`/jobs/${id}/documents${status ? `?status=${status}` : ''}`),
  duplicates: (id: string) => req<DuplicateRow[]>(`/jobs/${id}/duplicates`),
  invoice: (id: string) => req<Invoice>(`/invoices/${id}`),
  correct: (id: string, changes: Record<string, string | null>) =>
    req<Invoice & { changed: string[] }>(`/invoices/${id}`, json('PATCH', changes)),
  review: (id: string, reviewed: boolean) =>
    req<Invoice>(`/invoices/${id}/review`, json('POST', { reviewed })),
  createExports: (id: string, kinds: string[]) =>
    req<ExportRow[]>(`/jobs/${id}/exports`, json('POST', { kinds })),
  exports: (id: string) => req<ExportRow[]>(`/jobs/${id}/exports`),
  settings: () => req<Settings>('/settings'),
  saveOcr: (b: Record<string, unknown>) => req<Settings>('/settings/ocr', json('PUT', b)),
  saveAi: (b: Record<string, unknown>) => req<Settings>('/settings/ai', json('PUT', b)),
  testAi: () => req<{ ok: boolean; message: string }>('/settings/ai/test', { method: 'POST' }),
}

export const fileUrl = (docId: string) => `/api/documents/${docId}/file${tokenQuery()}`
export const downloadUrl = (exportId: string) => `/api/exports/${exportId}/download${tokenQuery()}`
