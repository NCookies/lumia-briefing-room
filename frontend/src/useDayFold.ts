import { useCallback, useEffect, useState } from 'react'
import { allCollapsed, collapseAll, loadCollapsed, revealDay, saveCollapsed, toggleDay, type DayScope, type DayShortcut } from './dayFold'

/** 날짜별 접힘 상태(탭마다 localStorage 에 기억)와 바로가기 이동. `days` 는 지금 화면에 나온 날짜 순서. */
export function useDayFold(scope: DayScope, days: (string | null)[]) {
  const [collapsed, setCollapsed] = useState(() => loadCollapsed(scope))
  const [pending, setPending] = useState<string | null>(null)

  const update = useCallback(
    (next: Set<string>) => {
      setCollapsed(next)
      saveCollapsed(scope, next)
    },
    [scope],
  )

  useEffect(() => {
    if (pending === null) return
    document.getElementById(pending)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    setPending(null)
  }, [pending])

  return {
    collapsed,
    toggle: (day: string | null) => update(toggleDay(collapsed, day)),
    collapseAll: () => update(collapseAll(days)),
    expandAll: () => update(new Set()),
    allCollapsed: allCollapsed(days, collapsed),
    go: (shortcut: DayShortcut) => {
      update(revealDay(collapsed, shortcut.day))
      setPending(shortcut.anchor)
    },
  }
}
