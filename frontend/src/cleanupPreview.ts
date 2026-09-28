export type CleanupReason = 'age' | 'count' | 'size'

export interface CleanupPreviewEntry {
  reason: CleanupReason
  dueAt: string | null
}

export type CleanupPreviewMap = Record<string, CleanupPreviewEntry>

const MS_PER_DAY = 24 * 60 * 60 * 1000

/** plan-ui.md §0 "자동 정리 삭제 예정 표시" — 나이 기준은 "N일 후", 개수·용량 기준은 "한도 초과로". */
export function cleanupReasonLabel(entry: CleanupPreviewEntry, now: Date = new Date()): string {
  if (entry.reason !== 'age' || !entry.dueAt) return '한도 초과로 삭제 예정'
  const daysLeft = Math.ceil((new Date(entry.dueAt).getTime() - now.getTime()) / MS_PER_DAY)
  return daysLeft <= 0 ? '곧 삭제 예정' : `${daysLeft}일 후 삭제 예정`
}

/** 개수·용량 기준은 클립 집합이 바뀌면 대상이 달라질 수 있다는 툴팁이 붙는다(§0 (4)). */
export function cleanupReasonTooltip(entry: CleanupPreviewEntry): string | undefined {
  return entry.reason === 'age' ? undefined : '클립 구성이 바뀌면 달라질 수 있는 현재 기준 예상입니다'
}

/** 게임 행 배지는 그 게임의 클립이 전부 삭제 예정일 때만 표시한다(§0 (1)) — 가장 급한(가까운) 사유를 고른다. */
export function gameCleanupEntry(clipIds: string[], preview: CleanupPreviewMap): CleanupPreviewEntry | null {
  if (clipIds.length === 0) return null
  const entries = clipIds.map((id) => preview[id])
  if (entries.some((e) => e === undefined)) return null

  const ageEntries = entries.filter((e): e is CleanupPreviewEntry => e.reason === 'age' && e.dueAt !== null)
  if (ageEntries.length > 0) {
    return ageEntries.reduce((soonest, e) => (e.dueAt! < soonest.dueAt! ? e : soonest))
  }
  return entries[0]
}
