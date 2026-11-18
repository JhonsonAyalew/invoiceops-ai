import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Download, FileSpreadsheet, FileText, FileType2, Table2 } from 'lucide-react'
import { api, downloadUrl } from '../api'
import { fmtBytes, fmtDate, useLoad } from '../hooks'
import { Card, Empty, ErrorBox, PageHeader, Spinner, useToast } from '../ui'

const KINDS = [
  {
    id: 'xlsx',
    title: 'Excel workbook',
    desc: 'Invoices, Line Items, Review Summary and Exceptions sheets.',
    icon: <FileSpreadsheet size={22} />,
  },
  {
    id: 'csv_invoices',
    title: 'Invoices CSV',
    desc: 'One row per invoice. UTF-8, ISO dates.',
    icon: <Table2 size={22} />,
  },
  {
    id: 'csv_line_items',
    title: 'Line items CSV',
    desc: 'Line items linked to invoice numbers.',
    icon: <FileType2 size={22} />,
  },
  {
    id: 'pdf_report',
    title: 'PDF processing report',
    desc: 'Client-ready summary with exceptions.',
    icon: <FileText size={22} />,
  },
]

export function ExportPanel({ jobId }: { jobId: string }) {
  const list = useLoad(() => api.exports(jobId), [jobId])
  const job = useLoad(() => api.job(jobId), [jobId])
  const [busy, setBusy] = useState<string | null>(null)
  const toast = useToast()
  const noData = !!job.data && job.data.counts.total === 0
  async function make(kinds: string[], label: string) {
    setBusy(label)
    try {
      await api.createExports(jobId, kinds)
      toast('ok', `${label} ready to download`)
      await list.reload()
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Export failed')
    } finally {
      setBusy(null)
    }
  }
  const unreviewed = job.data ? job.data.counts.needs_review : 0
  return (
    <>
      {unreviewed > 0 && (
        <div className="alert a-warn">
          {unreviewed} invoice(s) still need review. Exports will list them as "needs review"; the PDF report
          never claims manual review that did not happen.{' '}
          <Link to={`/jobs/${jobId}/review`}>Open review workspace</Link>
        </div>
      )}
      <div className="grid g2">
        {KINDS.map((k) => (
          <div className="card stat row gap" key={k.id} style={{ marginBottom: 0 }}>
            <div style={{ color: 'var(--accent)' }}>{k.icon}</div>
            <div className="grow">
              <b>{k.title}</b>
              <div className="muted">{k.desc}</div>
            </div>
            <button className="btn" disabled={!!busy || noData} onClick={() => void make([k.id], k.title)}>
              {busy === k.title ? 'Generating…' : 'Generate'}
            </button>
          </div>
        ))}
      </div>
      <div className="row" style={{ margin: '16px 0' }}>
        <button
          className="btn primary"
          disabled={!!busy || noData}
          onClick={() =>
            void make(
              KINDS.map((k) => k.id),
              'All deliverables',
            )
          }
        >
          {busy === 'All deliverables' ? 'Generating…' : 'Generate all four deliverables'}
        </button>
      </div>
      <Card title="Generated files" pad={false}>
        {list.loading && !list.data && <Spinner />}
        {list.error && <ErrorBox message={list.error} retry={list.reload} />}
        {list.data && list.data.length === 0 && (
          <Empty
            icon={<Download size={30} />}
            title="Nothing generated yet"
            text="Generate a deliverable above, then download it here."
          />
        )}
        {list.data && list.data.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>File</th>
                <th>Type</th>
                <th className="num">Size</th>
                <th>Created</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {list.data.map((e) => (
                <tr key={e.id}>
                  <td>
                    <b>{e.filename}</b>
                  </td>
                  <td>{KINDS.find((k) => k.id === e.kind)?.title ?? e.kind}</td>
                  <td className="num">{fmtBytes(e.size_bytes)}</td>
                  <td className="muted">{fmtDate(e.created_at)}</td>
                  <td style={{ textAlign: 'right' }}>
                    <a className="btn sm primary" href={downloadUrl(e.id)} download>
                      <Download size={13} /> Download
                    </a>
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

export default function ExportCenter() {
  const jobs = useLoad(api.jobs, [])
  const [sel, setSel] = useState('')
  const id = sel || jobs.data?.[0]?.id || ''
  return (
    <>
      <PageHeader title="Export center" sub="Generate and download the deliverables for a job." />
      {jobs.loading && !jobs.data && <Spinner />}
      {jobs.error && <ErrorBox message={jobs.error} retry={jobs.reload} />}
      {jobs.data && jobs.data.length === 0 && (
        <Empty title="No jobs yet" text="Create a job and process some invoices first." />
      )}
      {jobs.data && jobs.data.length > 0 && (
        <>
          <div className="field" style={{ maxWidth: 420 }}>
            <label className="f" htmlFor="jsel">
              Job
            </label>
            <select id="jsel" value={id} onChange={(e) => setSel(e.target.value)}>
              {jobs.data.map((j) => (
                <option key={j.id} value={j.id}>
                  {j.name}
                  {j.reference ? ` (${j.reference})` : ''}
                </option>
              ))}
            </select>
          </div>
          <ExportPanel jobId={id} />
        </>
      )}
    </>
  )
}
