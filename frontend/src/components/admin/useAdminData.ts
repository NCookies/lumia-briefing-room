import { useEffect, useRef, useState } from 'react'

export interface AdminData<T> {
  data: T | null
  error: string | null
  loading: boolean
}

export function useAdminData<T>(load: () => Promise<T>, deps: unknown[], active: boolean, tick: number): AdminData<T> {
  const [state, setState] = useState<AdminData<T>>({ data: null, error: null, loading: false })
  const loadRef = useRef(load)
  loadRef.current = load

  useEffect(() => {
    if (!active) return
    let cancelled = false
    setState((prev) => ({ ...prev, loading: true }))
    loadRef
      .current()
      .then((data) => {
        if (!cancelled) setState({ data, error: null, loading: false })
      })
      .catch((e) => {
        if (!cancelled) setState((prev) => ({ ...prev, error: e instanceof Error ? e.message : String(e), loading: false }))
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, tick, ...deps])

  return state
}
