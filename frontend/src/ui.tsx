import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, Info, Loader2, X } from 'lucide-react'
import type { Status } from './types'

const LABEL: Record<Status, string> = {
  queued: 'Queued',
  processing: 'Processing',
  processed: 'Processed',
  needs_review: 'Needs review',
  reviewed: 'Reviewed',
  failed: 'Failed',
  duplicate: 'Duplicate',
}
export const statusLabel = (s: Status) => LABEL[s]

export function StatusBadge({ status }: { status: Status }) {
  return (
    <span className={`badge b-${status}`}>
      {status === 'processing' && <Loader2 size={11} className="spin" />}
      {LABEL[status]}
    </span>
  )
}

export function PageHeader({ title, sub, actions }: { title: string; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {sub && <p className="muted">{sub}</p>}
      </div>
      {actions && <div className="row gap">{actions}</div>}
    </div>
  )
}

export const Card = ({
  title,
  children,
  right,
  pad = true,
}: {
  title?: string
  children: ReactNode
  right?: ReactNode
  pad?: boolean
}) => (
  <section className="card">
    {(title || right) && (
      <header className="card-h">
        <h3>{title}</h3>
        {right}
      </header>
    )}
    <div className={pad ? 'card-b' : ''}>{children}</div>
  </section>
)

export const Empty = ({
  icon,
  title,
  text,
  action,
}: {
  icon?: ReactNode
  title: string
  text?: string
  action?: ReactNode
}) => (
  <div className="empty">
    {icon}
    <h3>{title}</h3>
    {text && <p className="muted">{text}</p>}
    {action}
  </div>
)

export const Spinner = ({ label = 'Loading…' }: { label?: string }) => (
  <div className="loading">
    <Loader2 className="spin" size={18} /> {label}
  </div>
)

export const ErrorBox = ({ message, retry }: { message: string; retry?: () => void }) => (
  <div className="alert a-error" role="alert">
    <AlertTriangle size={16} />
    <span>{message}</span>
    {retry && (
      <button className="btn sm" onClick={retry}>
        Retry
      </button>
    )}
  </div>
)

export const Progress = ({ percent }: { percent: number }) => (
  <div className="bar" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
    <div style={{ width: `${percent}%` }} />
  </div>
)

export function Modal({
  title,
  children,
  onClose,
  footer,
}: {
  title: string
  children: ReactNode
  onClose: () => void
  footer: ReactNode
}) {
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <header className="card-h">
          <h3>{title}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </header>
        <div className="card-b">{children}</div>
        <footer className="modal-f">{footer}</footer>
      </div>
    </div>
  )
}

// ---- toasts
interface Toast {
  id: number
  kind: 'ok' | 'error' | 'info'
  text: string
}
const ToastCtx = createContext<(kind: Toast['kind'], text: string) => void>(() => {})
export const useToast = () => useContext(ToastCtx)
export function ToastProvider({ children }: { children: ReactNode }) {
  const [list, setList] = useState<Toast[]>([])
  const push = useCallback((kind: Toast['kind'], text: string) => {
    const id = Date.now() + Math.random()
    setList((l) => [...l, { id, kind, text }])
    setTimeout(() => setList((l) => l.filter((t) => t.id !== id)), kind === 'error' ? 7000 : 3500)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite">
        {list.map((t) => (
          <div key={t.id} className={`toast t-${t.kind}`}>
            {t.kind === 'ok' ? (
              <CheckCircle2 size={16} />
            ) : t.kind === 'error' ? (
              <AlertTriangle size={16} />
            ) : (
              <Info size={16} />
            )}
            {t.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}
