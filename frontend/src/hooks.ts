import { useCallback, useEffect, useRef, useState } from 'react'

/** Load data on mount / when deps change, optionally polling. Errors are surfaced, never swallowed. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[], pollMs = 0) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const fnRef = useRef(fn)
  fnRef.current = fn
  const reload = useCallback(async () => {
    try {
      setData(await fnRef.current())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => {
    setLoading(true)
    void reload()
    if (!pollMs) return
    const t = setInterval(() => void reload(), pollMs)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, pollMs, reload])
  return { data, error, loading, reload, setData }
}

export const fmtBytes = (n: number) =>
  n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`
export const fmtDate = (s: string | null | undefined) =>
  s ? new Date(s).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—'
export const fmtMoney = (v: string | null | undefined, cur?: string | null) => {
  if (v == null) return '—'
  const [i, d] = v.split('.')
  const neg = i.startsWith('-')
  const grouped = i.replace('-', '').replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${neg ? '-' : ''}${grouped}.${d ?? '00'}${cur ? ' ' + cur : ''}`
}
