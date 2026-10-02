import { useEffect, useRef, useState } from 'react'
import { isSearching } from './search'
import { useDebouncedValue } from './useDebouncedValue'

/** 목록 화면의 검색 상태. `applied` 는 0.3초 모인 검색어이고, 바뀌면(첫 그리기 제외) 탭이 보이는 동안 `onApplied` 로 목록을 다시 읽는다. */
export function useSearch(active: boolean, onApplied: () => void) {
  const [query, setQuery] = useState('')
  const applied = useDebouncedValue(query).trim()
  const appliedRef = useRef(applied)
  appliedRef.current = applied
  const last = useRef(applied)
  const reload = useRef(onApplied)
  reload.current = onApplied
  useEffect(() => {
    if (last.current === applied) return
    last.current = applied
    if (active) reload.current()
  }, [applied, active])
  return { query, setQuery, applied, appliedRef, searching: isSearching(applied) }
}
