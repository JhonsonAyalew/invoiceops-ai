import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Info,
  Save,
  Undo2,
  XCircle,
} from 'lucide-react'
import { api, fileUrl } from '../api'
import { fmtMoney, useLoad } from '../hooks'
import type { Doc, Invoice, Issue } from '../types'
import { Empty, ErrorBox, Spinner, StatusBadge, statusLabel, useToast } from '../ui'
import { STATUSES } from '../types'

type Kind = 'text' | 'date' | 'money' | 'area'
interface FieldDef {
  key: string
  label: string
  kind: Kind
  full?: boolean
  required?: boolean
}
const GROUPS: { title: string; fields: FieldDef[] }[] = [
  {
    title: 'Supplier',
    fields: [
      { key: 'supplier_name', label: 'Supplier name', kind: 'text', full: true, required: true },
      { key: 'supplier_address', label: 'Supplier address', kind: 'area', full: true },
      { key: 'supplier_tax_id', label: 'Supplier tax / VAT ID', kind: 'text' },
    ],
  },
  {
    title: 'Customer',
    fields: [
      { key: 'customer_name', label: 'Customer name', kind: 'text', full: true },
      { key: 'customer_address', label: 'Customer address', kind: 'area', full: true },
      { key: 'customer_tax_id', label: 'Customer tax / VAT ID', kind: 'text' },
    ],
  },
  {
    title: 'Invoice',
    fields: [
      { key: 'invoice_number', label: 'Invoice number', kind: 'text', required: true },
      { key: 'po_number', label: 'PO number', kind: 'text' },
      { key: 'invoice_date', label: 'Invoice date', kind: 'date', required: true },
      { key: 'due_date', label: 'Due date', kind: 'date' },
      { key: 'currency', label: 'Currency', kind: 'text', required: true },
      { key: 'payment_terms', label: 'Payment terms', kind: 'text' },
    ],
  },
  {
    title: 'Amounts',
    fields: [
      { key: 'subtotal', label: 'Subtotal', kind: 'money' },
      { key: 'discount', label: 'Discount', kind: 'money' },
      { key: 'shipping', label: 'Shipping', kind: 'money' },
      { key: 'tax_amount', label: 'Tax amount', kind: 'money' },
      { key: 'total_amount', label: 'Total', kind: 'money', required: true },
      { key: 'amount_paid', label: 'Amount paid', kind: 'money' },
      { key: 'balance_due', label: 'Balance due', kind: 'money' },
    ],
  },
  { title: 'Notes', fields: [{ key: 'notes', label: 'Description / notes', kind: 'area', full: true }] },
]
const ALL = GROUPS.flatMap((g) => g.fields)
const nz = (v: string | null | undefined) => v ?? ''

function IssueRow({ i }: { i: Issue }) {
  const icon =
    i.severity === 'error' ? (
      <XCircle size={14} />
    ) : i.severity === 'warning' ? (
      <AlertTriangle size={14} />
    ) : (
      <Info size={14} />
    )
  return (
    <div className={`issue i-${i.severity}`}>
      {icon}
      <span>{i.message}</span>
    </div>
  )
}

function Form({
  inv,
  onSaved,
  onNext,
  hasNext,
}: {
  inv: Invoice
  onSaved: (i: Invoice) => void
  onNext: () => void
  hasNext: boolean
}) {
  const toast = useToast()
  const [vals, setVals] = useState<Record<string, string>>(() =>
    Object.fromEntries(ALL.map((f) => [f.key, nz(inv.fields[f.key])])),
  )
  const [busy, setBusy] = useState(false)
  const diff = useMemo(() => {
    const d: Record<string, string | null> = {}
    for (const f of ALL)
      if (vals[f.key] !== nz(inv.fields[f.key])) d[f.key] = vals[f.key].trim() === '' ? null : vals[f.key]
    return d
  }, [vals, inv.fields])
  const dirty = Object.keys(diff).length > 0

  const save = useCallback(async (): Promise<Invoice | null> => {
    if (!dirty) return inv
    setBusy(true)
    try {
      const r = await api.correct(inv.id, diff)
      onSaved(r)
      setVals(Object.fromEntries(ALL.map((f) => [f.key, nz(r.fields[f.key])])))
      toast('ok', `Saved ${r.changed.length} change(s)`)
      return r
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Save failed')
      return null
    } finally {
      setBusy(false)
    }
  }, [dirty, diff, inv, onSaved, toast])

  async function markReviewed() {
    const saved = await save()
    if (!saved) return
    setBusy(true)
    try {
      onSaved(await api.review(inv.id, !inv.reviewed))
      toast('ok', inv.reviewed ? 'Review mark removed' : 'Marked as reviewed')
      if (!inv.reviewed && hasNext) onNext()
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Failed')
    } finally {
      setBusy(false)
    }
  }
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault()
        void save()
      }
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [save])

  const issues = inv.issues.filter((i) => i.severity !== 'info')
  const infos = inv.issues.filter((i) => i.severity === 'info')
  return (
    <>
      <div className="row gap wrap">
        <StatusBadge
          status={
            inv.reviewed
              ? 'reviewed'
              : inv.document.extraction_status === 'needs_review'
                ? 'needs_review'
                : 'processed'
          }
        />
        <span className="muted">Method: {inv.extraction_method}</span>
        {inv.reviewed && <span className="muted">· reviewed by you</span>}
      </div>
      <div className="grp">Validation</div>
      {issues.length === 0 && infos.length === 0 && (
        <div className="issue i-info">
          <CheckCircle2 size={14} /> No validation warnings.
        </div>
      )}
      {[...issues, ...infos].map((i, n) => (
        <IssueRow key={n} i={i} />
      ))}
      {GROUPS.map((g) => (
        <div key={g.title}>
          <div className="grp">{g.title}</div>
          <div className="fg">
            {g.fields.map((f) => {
              const v = vals[f.key]
              const meta = inv.meta[f.key]
              const orig = nz(inv.original[f.key])
              const edited = inv.edited_fields.includes(f.key) || v !== nz(inv.fields[f.key])
              const missing = v.trim() === ''
              const low = !missing && !edited && meta && meta.confidence < 0.7
              const ai = meta?.source?.startsWith('ai') && !edited
              const cls = missing && f.required ? 'in-miss' : edited ? 'in-edit' : low ? 'in-low' : ''
              const common = {
                id: `f-${f.key}`,
                className: cls,
                value: v,
                onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
                  setVals((s) => ({ ...s, [f.key]: e.target.value })),
              }
              return (
                <div key={f.key} className={f.full ? 'full' : ''}>
                  <div className="fl">
                    <label htmlFor={`f-${f.key}`}>{f.label}</label>
                    <span>
                      {missing && f.required && <span className="tag tg-miss">missing</span>}
                      {low && (
                        <span className="tag tg-miss" title={meta?.evidence}>
                          check
                        </span>
                      )}
                      {ai && <span className="tag tg-ai">AI</span>}
                      {edited && <span className="tag tg-edit">edited</span>}
                    </span>
                  </div>
                  {f.kind === 'area' ? (
                    <textarea rows={2} {...common} />
                  ) : (
                    <input
                      {...common}
                      type={f.kind === 'date' ? 'date' : 'text'}
                      inputMode={f.kind === 'money' ? 'decimal' : undefined}
                    />
                  )}
                  {edited && orig !== v && <div className="hint">Extracted: {orig || '(blank)'}</div>}
                </div>
              )
            })}
          </div>
        </div>
      ))}
      <div className="grp">Line items ({inv.line_items.length})</div>
      {inv.line_items.length === 0 ? (
        <div className="muted">No line items were extracted.</div>
      ) : (
        <div style={{ overflowX: 'auto', border: '1px solid var(--line)', borderRadius: 9 }}>
          <table>
            <thead>
              <tr>
                <th>Description</th>
                <th className="num">Qty</th>
                <th className="num">Unit</th>
                <th className="num">Total</th>
              </tr>
            </thead>
            <tbody>
              {inv.line_items.map((l, n) => (
                <tr
                  key={n}
                  style={l.reliable ? undefined : { background: 'var(--warn-bg)' }}
                  title={l.note ?? undefined}
                >
                  <td>
                    {l.description}
                    {!l.reliable && <div className="hint">⚠ {l.note}</div>}
                  </td>
                  <td className="num">{l.quantity ?? '—'}</td>
                  <td className="num">{fmtMoney(l.unit_price)}</td>
                  <td className="num">{fmtMoney(l.line_total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="rv-bar">
        <button
          className="btn"
          disabled={!dirty || busy}
          onClick={() => setVals(Object.fromEntries(ALL.map((f) => [f.key, nz(inv.fields[f.key])])))}
        >
          <Undo2 size={14} /> Discard
        </button>
        <button className="btn" disabled={!dirty || busy} onClick={() => void save()}>
          <Save size={14} /> Save{dirty ? ` (${Object.keys(diff).length})` : ''}
        </button>
        <button className="btn primary right" disabled={busy} onClick={() => void markReviewed()}>
          <CheckCircle2 size={14} />{' '}
          {inv.reviewed ? 'Remove reviewed mark' : hasNext ? 'Mark reviewed & next' : 'Mark reviewed'}
        </button>
      </div>
    </>
  )
}

export default function Review() {
  const { id = '', invoiceId } = useParams()
  const nav = useNavigate()
  const [filter, setFilter] = useState('all')
  const docs = useLoad(() => api.documents(id), [id])
  const inv = useLoad(() => (invoiceId ? api.invoice(invoiceId) : Promise.resolve(null)), [invoiceId])
  const list: Doc[] = useMemo(
    () => (docs.data ?? []).filter((d) => filter === 'all' || d.status === filter),
    [docs.data, filter],
  )
  const navigable = list.filter((d) => d.invoice_id)
  const idx = navigable.findIndex((d) => d.invoice_id === invoiceId)
  const go = (d?: Doc) => d?.invoice_id && nav(`/jobs/${id}/review/${d.invoice_id}`)

  useEffect(() => {
    if (!invoiceId && docs.data) {
      const first =
        docs.data.find((d) => d.status === 'needs_review' && d.invoice_id) ??
        docs.data.find((d) => d.invoice_id)
      if (first?.invoice_id) nav(`/jobs/${id}/review/${first.invoice_id}`, { replace: true })
    }
  }, [invoiceId, docs.data, id, nav])
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (!e.altKey) return
      if (e.key === 'ArrowRight') go(navigable[idx + 1])
      if (e.key === 'ArrowLeft') go(navigable[idx - 1])
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  })
  const onSaved = useCallback(
    (i: Invoice) => {
      inv.setData(i)
      docs.setData(
        (d) =>
          d && d.map((x) => (x.invoice_id === i.id ? { ...x, ...i.document, status: i.document.status } : x)),
      )
    },
    [inv, docs],
  )

  const counts: Record<string, number> = {}
  docs.data?.forEach((d) => (counts[d.status] = (counts[d.status] ?? 0) + 1))
  const doc = inv.data?.document

  return (
    <>
      <div
        className="row gap"
        style={{ padding: '12px 18px', background: '#fff', borderBottom: '1px solid var(--line)' }}
      >
        <Link className="btn sm" to={`/jobs/${id}/results`}>
          <ArrowLeft size={13} /> Results
        </Link>
        <b>Review workspace</b>
        <span className="muted">{idx >= 0 ? `${idx + 1} of ${navigable.length}` : ''}</span>
        <div className="right row gap">
          <button
            className="btn sm"
            disabled={idx <= 0}
            onClick={() => go(navigable[idx - 1])}
            title="Alt + ←"
          >
            <ChevronLeft size={14} /> Prev
          </button>
          <button
            className="btn sm"
            disabled={idx < 0 || idx >= navigable.length - 1}
            onClick={() => go(navigable[idx + 1])}
            title="Alt + →"
          >
            Next <ChevronRight size={14} />
          </button>
        </div>
      </div>
      {docs.loading && !docs.data && <Spinner />}
      {docs.error && <ErrorBox message={docs.error} retry={docs.reload} />}
      {docs.data && docs.data.length === 0 && (
        <Empty title="No documents in this job" text="Upload invoices first." />
      )}
      {docs.data && docs.data.length > 0 && (
        <div className="rv">
          <div className="rv-list">
            <div style={{ padding: 10, borderBottom: '1px solid var(--line)' }}>
              <select
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                aria-label="Filter by status"
              >
                <option value="all">All documents ({docs.data.length})</option>
                {STATUSES.filter((s) => counts[s]).map((s) => (
                  <option key={s} value={s}>
                    {statusLabel(s)} ({counts[s]})
                  </option>
                ))}
              </select>
            </div>
            {list.length === 0 && (
              <div className="muted" style={{ padding: 14 }}>
                No documents with this status.
              </div>
            )}
            {list.map((d) => (
              <button
                key={d.id}
                className={`rv-item${d.invoice_id === invoiceId ? ' on' : ''}`}
                disabled={!d.invoice_id}
                style={d.invoice_id ? undefined : { opacity: 0.6, cursor: 'default' }}
                onClick={() => go(d)}
              >
                <div
                  style={{
                    fontWeight: 600,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {d.supplier_name ?? d.name}
                </div>
                <div
                  className="muted"
                  style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                >
                  {d.invoice_number ?? d.error ?? d.name}
                </div>
                <div style={{ marginTop: 5 }}>
                  <StatusBadge status={d.status} />
                </div>
              </button>
            ))}
          </div>
          <div className="rv-pdf">
            {doc ? (
              <iframe
                title="Original PDF"
                src={`${fileUrl(doc.id)}${inv.data?.source_page ? '#page=' + inv.data.source_page : ''}`}
              />
            ) : (
              <div className="muted" style={{ margin: 'auto', color: '#cbd2e0' }}>
                Select an invoice
              </div>
            )}
          </div>
          <div className="rv-form">
            {inv.loading && !inv.data && invoiceId && <Spinner />}
            {inv.error && <ErrorBox message={inv.error} retry={inv.reload} />}
            {inv.data && (
              <Form
                key={inv.data.id}
                inv={inv.data}
                onSaved={onSaved}
                hasNext={idx >= 0 && idx < navigable.length - 1}
                onNext={() => go(navigable[idx + 1])}
              />
            )}
            {!invoiceId && !inv.loading && (
              <Empty
                title="Nothing to review yet"
                text="Documents that failed processing have no extracted data."
              />
            )}
          </div>
        </div>
      )}
    </>
  )
}
