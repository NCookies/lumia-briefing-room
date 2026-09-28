import type { Vod } from './vodGrouping'

/** 영상의 날짜(YYYY-MM-DD)를 필터 바 칩용 짧은 표기(`9/27`)로 바꾼다. (plan-vod.md V8) */
export function formatDateChip(dateIso: string): string {
  const [, month, day] = dateIso.split('-')
  return `${Number(month)}/${Number(day)}`
}

/** 목록에 있는 영상들의 날짜를 오래된 순으로 중복 없이 뽑는다. 날짜를 모르는 영상은 뺀다. */
export function uniqueVideoDates(vods: Pick<Vod, 'videoDate'>[]): string[] {
  const dates = new Set<string>()
  for (const v of vods) {
    if (v.videoDate) dates.add(v.videoDate)
  }
  return [...dates].sort()
}

/** 선택된 날짜가 없으면(전체 보기) 항상 통과, 있으면 그 영상의 날짜가 선택된 날짜 중 하나여야 한다. */
export function matchesDateFilter(videoDate: string | null, selectedDates: string[]): boolean {
  if (selectedDates.length === 0) return true
  return videoDate !== null && selectedDates.includes(videoDate)
}
