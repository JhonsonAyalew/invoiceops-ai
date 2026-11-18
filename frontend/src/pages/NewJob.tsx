import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FileUp, X } from 'lucide-react'
import { api } from '../api'
import { fmtBytes, useLoad } from '../hooks'
import { Card, PageHeader, Progress, useToast } from '../ui'

const BATCH = 15

export default function NewJob() {
  const nav = useNavigate()
  const toast = useToast()
  const settings = useLoad(api.settings, [])
  const [name, setName] = useState('')
  const [ref, setRef] = useState('')
  const [note, setNote] = useState('')
  const [useAi, setUseAi] = useState(false)
  const [cloudConsent, setCloudConsent] = useState(false)
  const [files, setFiles] = useState<File[]>([])
  const [over, setOver] = useState(false)
  const [busy, setBusy] = useState(false)
  const [pct, setPct] = useState(0)
  const [stage, setStage] = useState('')
  const input = useRef<HTMLInputElement>(null)
  const ai = settings.data?.ai
  const keyMissing = ai?.provider === 'groq' && !ai.groq_key_configured
  const aiOff = !ai || ai.provider === 'none' || keyMissing
  const cloudAi = !!ai && ai.is_cloud && !aiOff

  const add = (list: FileList | null) => {
    if (!list) return
    const ok = Array.from(list).filter((f) => /\.(pdf|zip)$/i.test(f.name))
    if (ok.length < list.length)
      toast('info', `${list.length - ok.length} file(s) skipped: only PDF and ZIP are accepted`)
    setFiles((cur) => [...cur, ...ok])
  }
  const canGo = name.trim() && files.length > 0 && !busy

  async function go() {
    setBusy(true)
    try {
      const wantCloud = useAi && cloudAi
      if (wantCloud && !cloudConsent) {
        toast('error', `Cloud AI (${ai?.provider}) needs your authorisation for this job.`)
        setBusy(false)
        return
      }
      const job = await api.createJob({
        name: name.trim(),
        reference: ref.trim() || undefined,
        client_note: note.trim() || undefined,
        use_ai: useAi && !aiOff,
      })
      if (wantCloud && ai) {
        await api.consent(job.id, ai.provider)
      }
      for (let i = 0; i < files.length; i += BATCH) {
        setStage(`Uploading ${Math.min(i + BATCH, files.length)} of ${files.length}…`)
        await api.upload(job.id, files.slice(i, i + BATCH))
        setPct(Math.round((100 * Math.min(i + BATCH, files.length)) / files.length))
      }
      setStage('Starting extraction…')
      try {
        await api.process(job.id)
      } catch (e) {
        toast('info', e instanceof Error ? e.message : 'Nothing to process')
      }
      nav(`/jobs/${job.id}/monitor`)
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Upload failed')
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader
        title="New job"
        sub="Create a job for one client order, add the PDFs, and start extraction."
      />
      <div className="grid g2" style={{ alignItems: 'start' }}>
        <Card title="1. Order details">
          <div className="field">
            <label className="f" htmlFor="jn">
              Job name *
            </label>
            <input
              id="jn"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Acme Ltd – March invoices"
              maxLength={200}
            />
          </div>
          <div className="field">
            <label className="f" htmlFor="jr">
              Order reference
            </label>
            <input
              id="jr"
              value={ref}
              onChange={(e) => setRef(e.target.value)}
              placeholder="Fiverr order number"
              maxLength={100}
            />
          </div>
          <div className="field">
            <label className="f" htmlFor="jc">
              Internal note
            </label>
            <textarea
              id="jc"
              rows={3}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={2000}
            />
          </div>
          <div className="field">
            <label className="check">
              <input
                type="checkbox"
                checked={useAi && !aiOff}
                disabled={aiOff}
                onChange={(e) => setUseAi(e.target.checked)}
              />
              <span>
                <b>Use AI assistance on every invoice</b>
                <div className="hint">
                  {aiOff
                    ? keyMissing
                      ? 'Groq is selected but GROQ_API_KEY is missing. Add it to .env and restart, or pick Ollama.'
                      : 'No AI provider is configured (Settings → AI providers). Rules and OCR only.'
                    : `Provider: ${ai?.provider}${ai?.is_cloud ? ' (cloud)' : ' (local)'}. Runs on every document when enabled.`}
                </div>
              </span>
            </label>
          </div>
          {useAi && !aiOff && ai?.is_cloud && (
            <div className="field">
              <label className="check">
                <input
                  type="checkbox"
                  checked={cloudConsent}
                  onChange={(e) => setCloudConsent(e.target.checked)}
                />
                <span>
                  <b>Allow sending document text to {ai.provider}</b>
                  <div className="hint">
                    Required for cloud AI. This authorisation is recorded for this job only.
                  </div>
                </span>
              </label>
            </div>
          )}
        </Card>
        <Card title="2. Invoices">
          <div
            className={`drop${over ? ' over' : ''}`}
            onClick={() => input.current?.click()}
            onDragOver={(e) => {
              e.preventDefault()
              setOver(true)
            }}
            onDragLeave={() => setOver(false)}
            onDrop={(e) => {
              e.preventDefault()
              setOver(false)
              add(e.dataTransfer.files)
            }}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === 'Enter' && input.current?.click()}
          >
            <FileUp size={30} color="#2a9d8f" />
            <h3 style={{ marginTop: 8 }}>Drop PDFs or a ZIP here, or click to browse</h3>
            <p className="muted">Hundreds of files are fine. ZIPs are unpacked safely.</p>
            <input
              ref={input}
              type="file"
              multiple
              accept=".pdf,.zip,application/pdf,application/zip"
              hidden
              onChange={(e) => {
                add(e.target.files)
                e.target.value = ''
              }}
            />
          </div>
          {files.length > 0 && (
            <>
              <div className="row" style={{ margin: '14px 0 6px' }}>
                <b>{files.length} file(s)</b>
                <span className="muted" style={{ marginLeft: 8 }}>
                  {fmtBytes(files.reduce((a, f) => a + f.size, 0))}
                </span>
                <button className="btn sm right" onClick={() => setFiles([])} disabled={busy}>
                  Clear
                </button>
              </div>
              <div
                style={{ maxHeight: 220, overflow: 'auto', border: '1px solid var(--line)', borderRadius: 9 }}
              >
                <table>
                  <tbody>
                    {files.map((f, i) => (
                      <tr key={i}>
                        <td>{f.name}</td>
                        <td className="muted num">{fmtBytes(f.size)}</td>
                        <td style={{ width: 34 }}>
                          <button
                            className="icon-btn"
                            disabled={busy}
                            onClick={() => setFiles((l) => l.filter((_, j) => j !== i))}
                            aria-label="Remove"
                          >
                            <X size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
          {busy && (
            <div style={{ marginTop: 14 }}>
              <div className="muted" style={{ marginBottom: 6 }}>
                {stage}
              </div>
              <Progress percent={pct} />
            </div>
          )}
          <button
            className="btn primary"
            style={{ marginTop: 16 }}
            disabled={!canGo}
            onClick={() => void go()}
          >
            Create job &amp; start extraction
          </button>
        </Card>
      </div>
    </>
  )
}
