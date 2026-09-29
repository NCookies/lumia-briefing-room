export interface DayGroup<T> {
  day: string | null
  games: T[]
}

const WEEKDAYS = '일월화수목금토'

const pad = (n: number) => String(n).padStart(2, '0')

function dayKeyOfDate(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** 게임 시작 시각의 로컬 날짜(`YYYY-MM-DD`). 자정 기준으로 나눈다(사용자 결정, 2026-09-30). */
export function localDayKey(iso: string): string | null {
  if (!iso) return null
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? null : dayKeyOfDate(d)
}

/** 이미 정렬된 게임 목록을 순서 그대로 날짜 묶음으로 나눈다. 시각을 모르는 게임은 맨 뒤 한 묶음. */
export function groupByDay<T extends { matchStartUtc: string }>(games: T[]): DayGroup<T>[] {
  const days: DayGroup<T>[] = []
  const unknown: T[] = []
  for (const game of games) {
    const day = localDayKey(game.matchStartUtc)
    if (day === null) {
      unknown.push(game)
      continue
    }
    const last = days[days.length - 1]
    if (last && last.day === day) last.games.push(game)
    else days.push({ day, games: [game] })
  }
  if (unknown.length > 0) days.push({ day: null, games: unknown })
  return days
}

export function formatDayLabel(day: string | null, now: Date = new Date()): string {
  if (day === null) return '날짜 모름'
  const [y, m, d] = day.split('-').map(Number)
  const date = new Date(y, m - 1, d)
  const base = `${m}월 ${d}일 (${WEEKDAYS[date.getDay()]})`
  const label = y === now.getFullYear() ? base : `${y}년 ${base}`
  const today = dayKeyOfDate(now)
  const yesterday = dayKeyOfDate(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1))
  if (day === today) return `${label} · 오늘`
  if (day === yesterday) return `${label} · 어제`
  return label
}
