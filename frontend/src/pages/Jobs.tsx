import { useState } from 'react'
import { Link } from 'react-router-dom'
import { FilePlus2, Layers, Trash2 } from 'lucide-react'
import { api } from '../api'
import { fmtDate, useLoad } from '../hooks'
import type { Job } from '../types'
import { Card, Empty, ErrorBox, Modal, PageHeader, Spinner, useToast } from '../ui'

export default function Jobs() {
  const { data, error, loading, reload } = useLoad(api.jobs, [], 5000)
  const [del, setDel] = useState<Job | null>(null)
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  async function remove() {
    if (!del) return
    setBusy(true)
    try {
      await api.deleteJob(del.id)
      toast('ok', `Deleted "${del.name}" and all of its files`)
      setDel(null)
      await reload()
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Delete failed')
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <PageHeader
        title="Jobs"
        sub="One job per Fiverr order. Documents never mix between jobs."
        actions={
          <Link className="btn primary" to="/jobs/new">
            <FilePlus2 size={15} /> New job
          </Link>
        }
      />
      {loading && !data && <Spinner />}
      {error && <ErrorBox message={error} retry={reload} />}
      {data && (
        <Card pad={false}>
          {data.length === 0 ? (
            <Empty
              icon={<Layers size={32} />}
              title="No jobs yet"
              text="Create a job to start processing invoices."
            />
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Job</th>
                  <th className="num">Docs</th>
                  <th className="num">Needs review</th>
                  <th className="num">Reviewed</th>
                  <th className="num">Failed</th>
                  <th>Created</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.map((j) => (
                  <tr key={j.id}>
                    <td>
                      <Link to={`/jobs/${j.id}`}>
                        <b>{j.name}</b>
                      </Link>
                      <div className="muted">{j.reference ?? 'No reference'}</div>
                    </td>
                    <td className="num">{j.counts.total}</td>
                    <td className="num">{j.counts.needs_review}</td>
                    <td className="num">{j.counts.reviewed}</td>
                    <td className="num">{j.counts.failed}</td>
                    <td className="muted">{fmtDate(j.created_at)}</td>
                    <td className="row gap" style={{ justifyContent: 'flex-end' }}>
                      <Link className="btn sm" to={`/jobs/${j.id}/results`}>
                        Results
                      </Link>
                      <Link className="btn sm" to={`/jobs/${j.id}/exports`}>
                        Exports
                      </Link>
                      <button
                        className="btn sm danger"
                        onClick={() => setDel(j)}
                        aria-label={`Delete ${j.name}`}
                      >
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      )}
      {del && (
        <Modal
          title="Delete job?"
          onClose={() => setDel(null)}
          footer={
            <>
              <button className="btn" onClick={() => setDel(null)}>
                Cancel
              </button>
              <button className="btn danger solid" disabled={busy} onClick={() => void remove()}>
                {busy ? 'Deleting…' : 'Delete permanently'}
              </button>
            </>
          }
        >
          <p>
            This permanently deletes <b>{del.name}</b>: {del.counts.total} document(s), extracted data,
            corrections and generated exports. This cannot be undone.
          </p>
        </Modal>
      )}
    </>
  )
}
