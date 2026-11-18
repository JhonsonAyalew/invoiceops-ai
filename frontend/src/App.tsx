import { useEffect, useState } from 'react'
import { NavLink, Navigate, Route, Routes, useMatch } from 'react-router-dom'
import {
  Cpu,
  FilePlus2,
  FileSpreadsheet,
  FileText,
  LayoutDashboard,
  Layers,
  ScanLine,
  Settings2,
  Sparkles,
} from 'lucide-react'
import { setToken } from './api'
import Overview from './pages/Overview'
import Jobs from './pages/Jobs'
import NewJob from './pages/NewJob'
import { JobShell, Monitor, Results, JobExports } from './pages/JobPages'
import Review from './pages/Review'
import ExportCenter from './pages/ExportCenter'
import { AiSettings, AppSettings, OcrSettings } from './pages/SettingsPages'

const Nav = ({ to, icon, children }: { to: string; icon: React.ReactNode; children: React.ReactNode }) => (
  <NavLink to={to} end={to === '/'} className={({ isActive }) => `nav${isActive ? ' active' : ''}`}>
    {icon}
    {children}
  </NavLink>
)

function TokenGate({ onDone }: { onDone: () => void }) {
  const [v, setV] = useState('')
  return (
    <div className="modal-bg">
      <form
        className="modal"
        onSubmit={(e) => {
          e.preventDefault()
          setToken(v.trim())
          onDone()
        }}
      >
        <header className="card-h">
          <h3>Admin token required</h3>
        </header>
        <div className="card-b">
          <p className="muted">
            This InvoiceOps instance is protected. Enter the ADMIN_TOKEN from your .env file.
          </p>
          <input
            type="password"
            autoFocus
            value={v}
            onChange={(e) => setV(e.target.value)}
            placeholder="Admin token"
          />
        </div>
        <footer className="modal-f">
          <button className="btn primary" type="submit">
            Continue
          </button>
        </footer>
      </form>
    </div>
  )
}

export default function App() {
  const [needAuth, setNeedAuth] = useState(false)
  const [epoch, setEpoch] = useState(0)
  const review = useMatch('/jobs/:id/review/*')
  useEffect(() => {
    const h = () => setNeedAuth(true)
    window.addEventListener('auth-required', h)
    return () => window.removeEventListener('auth-required', h)
  }, [])
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">
            <ScanLine size={18} />
          </span>
          InvoiceOps AI
        </div>
        <Nav to="/" icon={<LayoutDashboard size={17} />}>
          Overview
        </Nav>
        <Nav to="/jobs" icon={<Layers size={17} />}>
          Jobs
        </Nav>
        <Nav to="/jobs/new" icon={<FilePlus2 size={17} />}>
          New job &amp; upload
        </Nav>
        <Nav to="/exports" icon={<FileSpreadsheet size={17} />}>
          Export center
        </Nav>
        <div className="nav-sec">Settings</div>
        <Nav to="/settings/app" icon={<Settings2 size={17} />}>
          Application
        </Nav>
        <Nav to="/settings/ai" icon={<Sparkles size={17} />}>
          AI providers
        </Nav>
        <Nav to="/settings/ocr" icon={<Cpu size={17} />}>
          OCR
        </Nav>
        <div style={{ flex: 1 }} />
        <div className="muted mono" style={{ padding: 10, color: '#8391b0' }}>
          <FileText size={12} /> Local-first processing
        </div>
      </aside>
      <main className={`main${review ? ' flush' : ''}`} key={epoch}>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/jobs/new" element={<NewJob />} />
          <Route path="/jobs/:id" element={<JobShell />}>
            <Route index element={<Navigate to="monitor" replace />} />
            <Route path="monitor" element={<Monitor />} />
            <Route path="results" element={<Results />} />
            <Route path="exports" element={<JobExports />} />
          </Route>
          <Route path="/jobs/:id/review/:invoiceId?" element={<Review />} />
          <Route path="/exports" element={<ExportCenter />} />
          <Route path="/settings/app" element={<AppSettings />} />
          <Route path="/settings/ai" element={<AiSettings />} />
          <Route path="/settings/ocr" element={<OcrSettings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      {needAuth && (
        <TokenGate
          onDone={() => {
            setNeedAuth(false)
            setEpoch((e) => e + 1)
          }}
        />
      )}
    </div>
  )
}
