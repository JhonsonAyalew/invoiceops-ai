import { useMemo, useState } from 'react'
import { Link, NavLink, Outlet, useNavigate, useParams } from 'react-router-dom'
import {
  Activity,
  CheckCircle2,
  Cloud,
  FileSpreadsheet,
  ListChecks,
  Play,
  RotateCw,
  Search,
  Table2,
} from 'lucide-react'
import { api } from '../api'
import { fmtBytes, fmtMoney, useLoad } from '../hooks'
import { STATUSES, type Status } from '../types'
import {
  Card,
  Empty,
  ErrorBox,
  PageHeader,
  Progress,
  Spinner,
  StatusBadge,
  statusLabel,
  useToast,
} from '../ui'
import { ExportPanel } from './ExportCenter'

export function JobShell() {
  const { id = '' } = useParams()
  const { data, error, loading, reload } = useLoad(() => api.job(id), [id], 4000)
  const st = useLoad(api.settings, [])
  const toast = useToast()
  const [granting, setGranting] = useState(false)
  if (loading && !data) return <Spinner />
  if (error && !data) return <ErrorBox message={error} retry={reload} />
  if (!data) return null
  const ai = st.data?.ai
  const needsConsent = data.use_ai && ai?.is_cloud && data.ai_consent_provider !== ai.provider
  async function grant() {
    if (!ai) return
    setGranting(true)
    try {
      await api.consent(id, ai.provider)
      toast('ok', `Cloud AI authorised for ${ai.provider}`)
      await reload()
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Could not authorise cloud AI')
    } finally {
      setGranting(false)
    }
  }
  const tab = (to: string, icon: React.ReactNode, label: string) => (
    <NavLink to={to} className={({ isActive }) => `tab${isActive ? ' active' : ''}`}>
      {icon}
      {label}
    </NavLink>
  )
  return (
    <>
      <PageHeader
        title={data.name}
        sub={
          <>
            {data.reference ? `Order ${data.reference} · ` : ''}
            {data.counts.total} document(s)
            {data.ai_consent_provider
              ? ` · cloud AI authorised (${data.ai_consent_provider})`
              : data.use_ai
                ? ai?.is_cloud
                  ? ` · cloud AI (${ai.provider}) — consent needed`
                  : ' · local AI'
                : ''}
          </>
        }
        actions={
          <Link className="btn primary" to={`/jobs/${id}/review`}>
            <ListChecks size={15} /> Review workspace
          </Link>
        }
      />
      {needsConsent && (
        <div className="alert a-warn" style={{ marginBottom: 14 }}>
          <Cloud size={16} />
          <span className="grow">
            This job uses cloud AI ({ai?.provider}). Document text is sent only after you authorise this job.
          </span>
          <button className="btn sm primary" disabled={granting} onClick={() => void grant()}>
            Authorise {ai?.provider}
          </button>
        </div>
      )}
      <div className="tabs">
        {tab('monitor', <Activity size={15} />, 'Processing')}
        {tab('results', <Table2 size={15} />, 'Results')}
        {tab('exports', <FileSpreadsheet size={15} />, 'Exports')}
      </div>
      <Outlet />
    </>
  )
}

export function Monitor() {
  const { id = '' } = useParams()
  const prog = useLoad(() => api.progress(id), [id], 1500)
  const docs = useLoad(() => api.documents(id), [id], 2000)
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const nav = useNavigate()
  const c = prog.data?.counts
  async function start() {
    setBusy(true)
    try {
      const r = await api.process(id)
      toast('ok', `Started processing ${r.queued} document(s)`)
      await Promise.all([prog.reload(), docs.reload()])
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Could not start')
    } finally {
      setBusy(false)
    }
  }
  async function retry(docId: string) {
    try {
      await api.retry(docId)
      toast('info', 'Document re-queued')
      await Promise.all([prog.reload(), docs.reload()])
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Retry failed')
    }
  }
  if (prog.error && !prog.data) return <ErrorBox message={prog.error} retry={prog.reload} />
  return (
    <>
      <Card>
        <div className="row gap wrap">
          <div className="grow">
            <div className="row gap">
              <b style={{ fontSize: 18 }}>{prog.data?.percent ?? 0}%</b>
              <span className="muted">{prog.data?.active ? 'Processing…' : c && c.total ? 'Idle' : ''}</span>
            </div>
            <Progress percent={prog.data?.percent ?? 0} />
          </div>
          {c && c.queued > 0 && (
            <button className="btn primary" disabled={busy} onClick={() => void start()}>
              <Play size={14} /> Process {c.queued} queued
            </button>
          )}
          {c && c.total > 0 && !prog.data?.active && (
            <button className="btn" onClick={() => nav(`/jobs/${id}/results`)}>
              <CheckCircle2 size={14} /> View results
            </button>
          )}
        </div>
        {c && (
          <div className="chips" style={{ marginTop: 14 }}>
            {STATUSES.filter((s) => c[s] > 0).map((s) => (
              <span key={s} className={`badge b-${s}`}>
                {statusLabel(s)}: {c[s]}
              </span>
            ))}
          </div>
        )}
      </Card>
      <Card title="Documents" pad={false}>
        {docs.loading && !docs.data && <Spinner />}
        {docs.data && docs.data.length === 0 && (
          <Empty title="No documents" text="Upload PDFs from the New job page." />
        )}
        {docs.data && docs.data.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>File</th>
                <th className="num">Size</th>
                <th className="num">Pages</th>
                <th>Status</th>
                <th>Method</th>
                <th>Note</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {docs.data.map((d) => (
                <tr key={d.id}>
                  <td>
                    <b>{d.name}</b>
                  </td>
                  <td className="num">{d.size_bytes ? fmtBytes(d.size_bytes) : '—'}</td>
                  <td className="num">{d.pages || '—'}</td>
                  <td>
                    <StatusBadge status={d.status} />
                  </td>
                  <td>{d.method ?? '—'}</td>
                  <td className="muted">{d.error ?? ''}</td>
                  <td style={{ textAlign: 'right' }}>
                    {['failed', 'duplicate'].includes(d.status) && (
                      <button className="btn sm" onClick={() => void retry(d.id)}>
                        <RotateCw size={12} /> Retry
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  )
}

export function Results() {
  const { id = '' } = useParams()
  const docs = useLoad(() => api.documents(id), [id], 5000)
  const dups = useLoad(() => api.duplicates(id), [id], 8000)
  const [filter, setFilter] = useState<Status | 'all'>('all')
  const [q, setQ] = useState('')
  const counts = useMemo(() => {
    const m: Record<string, number> = {}
    docs.data?.forEach((d) => (m[d.status] = (m[d.status] ?? 0) + 1))
    return m
  }, [docs.data])
  const rows = (docs.data ?? []).filter(
    (d) =>
      (filter === 'all' || d.status === filter) &&
      (!q ||
        `${d.name} ${d.supplier_name ?? ''} ${d.invoice_number ?? ''}`
          .toLowerCase()
          .includes(q.toLowerCase())),
  )
  if (docs.loading && !docs.data) return <Spinner />
  if (docs.error && !docs.data) return <ErrorBox message={docs.error} retry={docs.reload} />
  return (
    <>
      <div className="row gap wrap" style={{ marginBottom: 14 }}>
        <div className="chips">
          <button className={`chip${filter === 'all' ? ' on' : ''}`} onClick={() => setFilter('all')}>
            All ({docs.data?.length ?? 0})
          </button>
          {STATUSES.filter((s) => counts[s]).map((s) => (
            <button key={s} className={`chip${filter === s ? ' on' : ''}`} onClick={() => setFilter(s)}>
              {statusLabel(s)} ({counts[s]})
            </button>
          ))}
        </div>
        <div className="right" style={{ position: 'relative', width: 260 }}>
          <Search size={14} style={{ position: 'absolute', left: 10, top: 11, color: '#99a3b8' }} />
          <input
            style={{ paddingLeft: 30 }}
            placeholder="Search file, supplier, number"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      </div>
      <Card pad={false}>
        {rows.length === 0 ? (
          <Empty
            title="No matching documents"
            text={
              docs.data?.length ? 'Try a different filter.' : 'Nothing has been uploaded to this job yet.'
            }
          />
        ) : (
          <table>
            <thead>
              <tr>
                <th>File</th>
                <th>Supplier</th>
                <th>Invoice no.</th>
                <th>Date</th>
                <th className="num">Total</th>
                <th>Status</th>
                <th className="num">Issues</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.id}>
                  <td>{d.name}</td>
                  <td>{d.supplier_name ?? '—'}</td>
                  <td>{d.invoice_number ?? '—'}</td>
                  <td>{d.invoice_date ?? '—'}</td>
                  <td className="num">{fmtMoney(d.total_amount, d.currency)}</td>
                  <td>
                    <StatusBadge status={d.status} />
                  </td>
                  <td className="num">{d.issue_count ?? '—'}</td>
                  <td style={{ textAlign: 'right' }}>
                    {d.invoice_id && (
                      <Link className="btn sm" to={`/jobs/${id}/review/${d.invoice_id}`}>
                        Review
                      </Link>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      {dups.data && dups.data.length > 0 && (
        <Card title={`Duplicate candidates (${dups.data.length})`} pad={false}>
          <table>
            <thead>
              <tr>
                <th>File A</th>
                <th>File B</th>
                <th>Type</th>
                <th className="num">Score</th>
              </tr>
            </thead>
            <tbody>
              {dups.data.map((d, i) => (
                <tr key={i}>
                  <td>{d.a}</td>
                  <td>{d.b}</td>
                  <td>
                    {d.kind === 'file'
                      ? 'Identical file'
                      : d.kind === 'invoice'
                        ? 'Same invoice number'
                        : 'Similar'}
                  </td>
                  <td className="num">{d.score.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  )
}

export function JobExports() {
  const { id = '' } = useParams()
  return <ExportPanel jobId={id} />
}
