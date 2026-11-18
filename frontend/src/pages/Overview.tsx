import { Link } from 'react-router-dom'
import { AlertTriangle, CheckCircle2, Copy, FilePlus2, FileStack, Layers, XCircle } from 'lucide-react'
import { api } from '../api'
import { fmtDate, useLoad } from '../hooks'
import { Card, Empty, ErrorBox, PageHeader, Progress, Spinner } from '../ui'

export default function Overview() {
  const { data, error, loading, reload } = useLoad(api.overview, [], 4000)
  if (loading && !data) return <Spinner />
  if (error && !data) return <ErrorBox message={error} retry={reload} />
  if (!data) return null
  const c = data.counts
  const stats = [
    { l: 'Jobs', v: data.jobs, i: <Layers size={14} /> },
    { l: 'Documents', v: data.documents, i: <FileStack size={14} /> },
    { l: 'Needs review', v: c.needs_review, i: <AlertTriangle size={14} /> },
    { l: 'Reviewed by you', v: c.reviewed, i: <CheckCircle2 size={14} /> },
    { l: 'Failed', v: c.failed, i: <XCircle size={14} /> },
    { l: 'Duplicate files', v: c.duplicate, i: <Copy size={14} /> },
    { l: 'In queue', v: c.queued + c.processing, i: <Layers size={14} /> },
    { l: 'Processed OK', v: c.processed, i: <CheckCircle2 size={14} /> },
  ]
  return (
    <>
      <PageHeader
        title="Overview"
        sub="Everything across your invoice extraction jobs."
        actions={
          <Link className="btn primary" to="/jobs/new">
            <FilePlus2 size={15} /> New job
          </Link>
        }
      />
      {error && <ErrorBox message={error} />}
      <div className="grid g4">
        {stats.map((s) => (
          <div key={s.l} className="card stat" style={{ marginBottom: 0 }}>
            <div className="v">{s.v}</div>
            <div className="l">
              {s.i} {s.l}
            </div>
          </div>
        ))}
      </div>
      <div style={{ height: 16 }} />
      <Card title="Recent jobs" pad={false} right={<Link to="/jobs">View all</Link>}>
        {data.recent_jobs.length === 0 ? (
          <Empty
            icon={<FilePlus2 size={32} />}
            title="No jobs yet"
            text="Create a job for a Fiverr order and upload the client's PDF invoices."
            action={
              <Link className="btn primary" to="/jobs/new">
                Create your first job
              </Link>
            }
          />
        ) : (
          <table>
            <thead>
              <tr>
                <th>Job</th>
                <th>Documents</th>
                <th style={{ width: 220 }}>Progress</th>
                <th>Needs review</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {data.recent_jobs.map((j) => {
                const open = j.counts.queued + j.counts.processing
                const pct = j.counts.total ? Math.round((100 * (j.counts.total - open)) / j.counts.total) : 0
                return (
                  <tr key={j.id}>
                    <td>
                      <Link to={`/jobs/${j.id}`}>
                        <b>{j.name}</b>
                      </Link>
                      <div className="muted">{j.reference ?? ''}</div>
                    </td>
                    <td>{j.counts.total}</td>
                    <td>
                      <Progress percent={pct} />
                    </td>
                    <td>{j.counts.needs_review}</td>
                    <td className="muted">{fmtDate(j.created_at)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </Card>
    </>
  )
}
