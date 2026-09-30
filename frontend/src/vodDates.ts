/** 영상의 날짜(YYYY-MM-DD)를 필터 바 칩용 짧은 표기(`9/27`)로 바꾼다. (plan-vod.md V8) */
export function formatDateChip(dateIso: string): string {
  const [, month, day] = dateIso.split('-')
  return `${Number(month)}/${Number(day)}`
}

export interface VodDateGroup<T> {
  day: string | null
  vods: T[]
}

/** 영상 묶음을 영상 날짜별로 나눈다. 날짜는 정렬 방향을 따르고, 한 날짜 안은 들어온 순서(이름순)를 유지한다. 날짜 없는 영상은 맨 뒤. */
export function groupVodsByDate<T extends { vod: { videoDate: string | null } | null }>(
  groups: T[],
  sort: 'asc' | 'desc',
): VodDateGroup<T>[] {
  const byDate = new Map<string, T[]>()
  const unknown: T[] = []
  for (const g of groups) {
    const day = g.vod?.videoDate ?? null
    if (day === null) unknown.push(g)
    else byDate.set(day, [...(byDate.get(day) ?? []), g])
  }
  const days = [...byDate.keys()].sort()
  if (sort === 'desc') days.reverse()
  const result: VodDateGroup<T>[] = days.map((day) => ({ day, vods: byDate.get(day) ?? [] }))
  if (unknown.length > 0) result.push({ day: null, vods: unknown })
  return result
}
