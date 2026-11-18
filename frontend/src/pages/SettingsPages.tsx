import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, Cloud, HardDrive } from 'lucide-react'
import { api } from '../api'
import { useLoad } from '../hooks'
import type { Settings } from '../types'
import { Card, ErrorBox, PageHeader, Spinner, useToast } from '../ui'

function useSettings() {
  return useLoad(api.settings, [])
}
const Row = ({ k, v }: { k: string; v: React.ReactNode }) => (
  <tr>
    <td className="muted" style={{ width: 240 }}>
      {k}
    </td>
    <td>{v}</td>
  </tr>
)

export function AppSettings() {
  const { data, error, loading, reload } = useSettings()
  if (loading && !data) return <Spinner />
  if (error || !data) return <ErrorBox message={error ?? 'Failed'} retry={reload} />
  const a = data.app
  return (
    <>
      <PageHeader
        title="Application settings"
        sub="Operational limits are set in the .env file and take effect on restart."
      />
      <Card title="Runtime configuration" pad={false}>
        <table>
          <tbody>
            <Row
              k="Admin token protection"
              v={
                a.auth_enabled ? (
                  <span className="badge b-processed">Enabled</span>
                ) : (
                  <span className="badge b-needs_review">Off (bind to localhost only)</span>
                )
              }
            />
            <Row
              k="Document retention"
              v={
                a.retention_days > 0
                  ? `${a.retention_days} days, then jobs are deleted automatically`
                  : 'Keep until you delete a job'
              }
            />
            <Row k="Max PDF size" v={`${a.max_upload_mb} MB`} />
            <Row k="Max files per ZIP" v={a.max_zip_files} />
            <Row k="Parallel processing workers" v={a.workers} />
          </tbody>
        </table>
      </Card>
      <Card title="Privacy">
        <p style={{ margin: 0 }}>
          Documents are stored per job under random internal file names and are only reachable through this
          application. Cloud AI is never used without per-job consent. Deleting a job removes its files,
          extracted data, corrections and exports.
        </p>
      </Card>
    </>
  )
}

export function AiSettings() {
  const { data, error, loading, reload, setData } = useSettings()
  const toast = useToast()
  const [f, setF] = useState<Settings['ai'] | null>(null)
  const [test, setTest] = useState<{ ok: boolean; message: string } | null>(null)
  useEffect(() => {
    if (data) setF(data.ai)
  }, [data])
  if (loading && !data) return <Spinner />
  if (error || !data || !f) return <ErrorBox message={error ?? 'Failed'} retry={reload} />
  const set = (k: 'provider' | 'ollama_url' | 'ollama_model' | 'groq_base_url' | 'groq_model', v: string) =>
    setF({ ...f, [k]: v })
  async function save() {
    if (!f) return
    try {
      setData(
        await api.saveAi({
          provider: f.provider,
          ollama_url: f.ollama_url,
          ollama_model: f.ollama_model,
          groq_base_url: f.groq_base_url,
          groq_model: f.groq_model,
        }),
      )
      toast('ok', 'AI settings saved')
      setTest(await api.testAi())
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Save failed')
    }
  }
  return (
    <>
      <PageHeader
        title="AI provider"
        sub="Ollama runs locally; Groq is a fast cloud API and needs per-job authorisation. AI runs on every document when enabled, and every value must appear in the document text."
      />
      <div className="grid g2" style={{ alignItems: 'start' }}>
        <Card title="Provider">
          <div className="field">
            <label className="f" htmlFor="prov">
              Active provider
            </label>
            <select id="prov" value={f.provider} onChange={(e) => set('provider', e.target.value)}>
              <option value="none">None — rules and OCR only</option>
              <option value="ollama">Ollama — local, nothing leaves this PC</option>
              <option value="groq">Groq — fast cloud API (needs consent)</option>
            </select>
          </div>
          {f.provider === 'ollama' && (
            <div className="alert a-ok">
              <HardDrive size={16} /> Local processing. Document text never leaves this PC.
            </div>
          )}
          {f.provider === 'groq' && (
            <div className={`alert ${f.groq_key_configured ? 'a-warn' : 'a-error'}`}>
              <Cloud size={16} /> Cloud processing: document text is sent to Groq. Each job needs explicit
              authorisation before AI runs.
              {!f.groq_key_configured && ' GROQ_API_KEY is missing in .env.'}
            </div>
          )}
          {f.provider === 'ollama' && (
            <>
              <div className="field">
                <label className="f" htmlFor="ou">
                  Ollama URL
                </label>
                <input id="ou" value={f.ollama_url} onChange={(e) => set('ollama_url', e.target.value)} />
              </div>
              <div className="field">
                <label className="f" htmlFor="om">
                  Ollama model
                </label>
                <input id="om" value={f.ollama_model} onChange={(e) => set('ollama_model', e.target.value)} />
              </div>
            </>
          )}
          {f.provider === 'groq' && (
            <>
              <div className="field">
                <label className="f" htmlFor="gm">
                  Groq model
                </label>
                <input
                  id="gm"
                  value={f.groq_model}
                  onChange={(e) => set('groq_model', e.target.value)}
                  placeholder="openai/gpt-oss-20b"
                />
                <div className="hint">
                  Fast default: openai/gpt-oss-20b. Stronger but slower: openai/gpt-oss-120b. The model must
                  be available to your API key.
                </div>
              </div>
              <div className="field">
                <label className="f" htmlFor="gb">
                  Groq API base
                </label>
                <input
                  id="gb"
                  value={f.groq_base_url}
                  onChange={(e) => set('groq_base_url', e.target.value)}
                />
                <div className="hint">
                  The API key is read from GROQ_API_KEY in .env and is never stored in the app database.
                  Restart the server after changing it.
                </div>
              </div>
            </>
          )}
          <div className="row gap">
            <button className="btn primary" onClick={() => void save()}>
              Save &amp; test
            </button>
            <button className="btn" onClick={() => void api.testAi().then(setTest)}>
              Test connection
            </button>
          </div>
          {test && (
            <div className={`alert ${test.ok ? 'a-ok' : 'a-error'}`} style={{ marginTop: 14 }}>
              {test.ok ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
              {test.message}
            </div>
          )}
        </Card>
      </div>
    </>
  )
}

export function OcrSettings() {
  const { data, error, loading, reload, setData } = useSettings()
  const toast = useToast()
  const [o, setO] = useState<Settings['ocr'] | null>(null)
  useEffect(() => {
    if (data) setO(data.ocr)
  }, [data])
  if (loading && !data) return <Spinner />
  if (error || !data || !o) return <ErrorBox message={error ?? 'Failed'} retry={reload} />
  const st = data.ocr_status
  const toggle = (l: string) =>
    setO({
      ...o,
      languages: o.languages.includes(l) ? o.languages.filter((x) => x !== l) : [...o.languages, l],
    })
  async function save() {
    if (!o) return
    try {
      setData(
        await api.saveOcr({
          languages: o.languages,
          model_dir: o.model_dir ?? '',
          device: o.device,
          poppler_path: o.poppler_path ?? '',
          timeout_seconds: o.timeout_seconds,
          dpi: o.dpi,
        }),
      )
      toast('ok', 'OCR settings saved')
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Save failed')
    }
  }
  return (
    <>
      <PageHeader
        title="OCR configuration"
        sub="PaddleOCR PP-OCRv6 Medium reads scanned PDFs. Native PDF text is always tried first."
      />
      <div className="grid g2" style={{ alignItems: 'start' }}>
        <Card title="Settings">
          <div className="field">
            <label className="f">Languages in scope</label>
            <div className="chips">
              {Object.entries(o.supported_languages).map(([k, n]) => (
                <button
                  key={k}
                  className={`chip${o.languages.includes(k) ? ' on' : ''}`}
                  onClick={() => toggle(k)}
                >
                  {n} ({k})
                </button>
              ))}
            </div>
            <div className="hint">
              The PP-OCRv6 Medium model is multilingual; this selection labels the document scope.
            </div>
          </div>
          <div className="field">
            <label className="f" htmlFor="md">
              PP-OCRv6 model folder
            </label>
            <input
              id="md"
              placeholder="C:\Users\you\AppData\Local\InvoiceOps\paddle_models"
              value={o.model_dir ?? ''}
              onChange={(e) => setO({ ...o, model_dir: e.target.value })}
            />
            <div className="hint">
              Folder containing PP-OCRv6_medium_det and PP-OCRv6_medium_rec. Empty uses the default cache.
            </div>
          </div>
          <div className="field">
            <label className="f" htmlFor="dev">
              Device
            </label>
            <select id="dev" value={o.device} onChange={(e) => setO({ ...o, device: e.target.value })}>
              <option value="cpu">CPU (recommended)</option>
              <option value="gpu">GPU (CUDA build required)</option>
            </select>
          </div>
          <div className="field">
            <label className="f" htmlFor="pp">
              Poppler bin folder
            </label>
            <input
              id="pp"
              placeholder="C:\poppler\Library\bin"
              value={o.poppler_path ?? ''}
              onChange={(e) => setO({ ...o, poppler_path: e.target.value })}
            />
          </div>
          <div className="grid g2">
            <div className="field">
              <label className="f" htmlFor="dpi">
                Render DPI
              </label>
              <input
                id="dpi"
                type="number"
                min={100}
                max={600}
                value={o.dpi}
                onChange={(e) => setO({ ...o, dpi: Number(e.target.value) })}
              />
            </div>
            <div className="field">
              <label className="f" htmlFor="to">
                Timeout per page (s)
              </label>
              <input
                id="to"
                type="number"
                min={5}
                max={1800}
                value={o.timeout_seconds}
                onChange={(e) => setO({ ...o, timeout_seconds: Number(e.target.value) })}
              />
            </div>
          </div>
          <button className="btn primary" onClick={() => void save()}>
            Save OCR settings
          </button>
        </Card>
        <Card
          title="Installation status"
          right={
            st.ready ? (
              <span className="badge b-processed">Ready</span>
            ) : (
              <span className="badge b-failed">Action needed</span>
            )
          }
        >
          <table>
            <tbody>
              <Row
                k="Engine"
                v={
                  st.package_found ? (
                    `PaddleOCR ${st.version ?? ''}`.trim()
                  ) : (
                    <span className="badge b-failed">Not installed</span>
                  )
                }
              />
              <Row k="Model" v={st.model} />
              <Row
                k="Detection / recognition"
                v={
                  st.det_model_found && st.rec_model_found ? (
                    <span className="badge b-processed">Loaded from disk</span>
                  ) : (
                    <span className="badge b-failed">Missing</span>
                  )
                }
              />
              <Row k="Model cache" v={<span className="mono">{st.model_dir ?? '—'}</span>} />
              <Row k="Device" v={st.device} />
              <Row k="Languages" v={st.languages.join(', ') || '—'} />
              <Row
                k="Poppler (PDF rendering)"
                v={
                  st.poppler_found ? (
                    <span className="badge b-processed">Found</span>
                  ) : (
                    <span className="badge b-failed">Not found</span>
                  )
                }
              />
            </tbody>
          </table>
          {st.problems.map((p, i) => (
            <div key={i} className="alert a-warn" style={{ marginTop: 10 }}>
              <AlertTriangle size={16} />
              {p}
            </div>
          ))}
          <button className="btn" style={{ marginTop: 12 }} onClick={() => void reload()}>
            Re-check
          </button>
        </Card>
      </div>
    </>
  )
}
