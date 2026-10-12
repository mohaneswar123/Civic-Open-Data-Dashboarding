import { useEffect, useState } from 'react'
import { api } from './api'

export interface Loadable<T> { data: T | null; error: string | null; loading: boolean }

/** GET a JSON endpoint; keeps the previous data visible while refetching (no skeleton flash). */
export function useApi<T>(path: string | null): Loadable<T> {
  const [state, setState] = useState<Loadable<T>>({ data: null, error: null, loading: !!path })
  useEffect(() => {
    if (!path) return
    let cancelled = false
    setState(s => ({ ...s, loading: true, error: null }))
    api<T>(path)
      .then(data => { if (!cancelled) setState({ data, error: null, loading: false }) })
      .catch(e => { if (!cancelled) setState(s => ({ ...s, error: e.message, loading: false })) })
    return () => { cancelled = true }
  }, [path])
  return state
}

export function useLocalState<T>(key: string, initial: T): [T, (v: T) => void] {
  const [v, setV] = useState<T>(() => {
    try { const s = localStorage.getItem(key); return s ? JSON.parse(s) as T : initial } catch { return initial }
  })
  const set = (nv: T) => { setV(nv); try { localStorage.setItem(key, JSON.stringify(nv)) } catch { /* ignore */ } }
  return [v, set]
}
