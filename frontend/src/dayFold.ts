const KEY_PREFIX = 'lumia.collapsedDays.'

type StorageLike = Pick<Storage, 'getItem' | 'setItem'>

export type DayScope = 'steam' | 'vod'

/** 날짜 묶음의 식별자. 날짜를 모르는 묶음은 `unknown`. */
export const dayId = (day: string | null): string => day ?? 'unknown'

/** 날짜 머리줄의 DOM id. 두 탭이 함께 마운트돼 있어도 겹치지 않게 탭 이름을 넣는다. */
export const dayAnchorId = (scope: DayScope, day: string | null): string => `day-${scope}-${dayId(day)}`

function defaultStorage(): StorageLike | null {
  try {
    return localStorage
  } catch {
    return null
  }
}

/** 접혀 있던 날짜. 저장된 적 없는 날짜(새 날짜)는 접힌 것이 아니므로 펼쳐진다. localStorage 접근은 실패해도 화면이 동작해야 한다. */
export function loadCollapsed(scope: DayScope, storage: StorageLike | null = defaultStorage()): Set<string> {
  try {
    const raw = storage?.getItem(KEY_PREFIX + scope)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return new Set(Array.isArray(parsed) ? parsed.filter((d): d is string => typeof d === 'string') : [])
  } catch {
    return new Set()
  }
}

export function saveCollapsed(scope: DayScope, collapsed: Set<string>, storage: StorageLike | null = defaultStorage()): void {
  try {
    storage?.setItem(KEY_PREFIX + scope, JSON.stringify([...collapsed]))
  } catch {
    // 저장하지 못해도 화면은 동작한다
  }
}

export function toggleDay(collapsed: Set<string>, day: string | null): Set<string> {
  const next = new Set(collapsed)
  const id = dayId(day)
  if (!next.delete(id)) next.add(id)
  return next
}

/** 검색 결과가 있는 날짜는 접혀 있어도 펼쳐 보인다(저장된 접힘 상태는 바뀌지 않는다). */
export function visibleCollapsed(collapsed: Set<string>, searching: boolean): Set<string> {
  return searching ? new Set() : collapsed
}

export function collapseAll(days: (string | null)[]): Set<string> {
  return new Set(days.map(dayId))
}

export function allCollapsed(days: (string | null)[], collapsed: Set<string>): boolean {
  return days.length > 0 && days.every((d) => collapsed.has(dayId(d)))
}

/** 바로가기로 이동하기 전에 그 날짜를 펼친다(이미 펼쳐져 있으면 그대로). */
export function revealDay(collapsed: Set<string>, day: string | null): Set<string> {
  const next = new Set(collapsed)
  next.delete(dayId(day))
  return next
}

const shortDate = (day: string): string => {
  const [, month, date] = day.split('-')
  return `${Number(month)}/${Number(date)}`
}

export interface DayShortcut {
  day: string | null
  label: string
  anchor: string
}

/** 화면에 나온 날짜 순서 그대로의 바로가기 목록. */
export function shortcutDays(days: (string | null)[], scope: DayScope = 'steam'): DayShortcut[] {
  return days.map((day) => ({
    day,
    label: day === null ? '날짜 모름' : shortDate(day),
    anchor: dayAnchorId(scope, day),
  }))
}
