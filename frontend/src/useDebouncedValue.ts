import { useEffect, useState } from 'react'
import { SEARCH_DEBOUNCE_MS } from './search'

/** 입력이 멈춘 뒤 0.3초 지나서야 바뀌는 값 — 타자마다 서버에 묻지 않으려고. */
export function useDebouncedValue<T>(value: T, delayMs: number = SEARCH_DEBOUNCE_MS): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])
  return debounced
}
