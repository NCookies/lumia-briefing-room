export const MIN_LENGTH = 1

export interface TrimRange {
  start: number
  end: number
}

export function clampRange(range: TrimRange, handle: 'start' | 'end', value: number, duration: number): TrimRange {
  if (handle === 'start') {
    return { start: Math.min(Math.max(value, 0), range.end - MIN_LENGTH), end: range.end }
  }
  return { start: range.start, end: Math.max(Math.min(value, duration), range.start + MIN_LENGTH) }
}

export function formatTime(seconds: number): string {
  const tenths = Math.round(seconds * 10)
  const m = Math.floor(tenths / 600)
  const s = (tenths % 600) / 10
  return `${m}:${s.toFixed(1).padStart(4, '0')}`
}

export function initialRange(playhead: number, duration: number): TrimRange {
  const start = Number.isFinite(playhead) && playhead <= duration - MIN_LENGTH ? Math.max(playhead, 0) : 0
  return { start, end: duration }
}

export interface RangeAdd {
  ranges: TrimRange[]
  index: number
}

function freeGaps(ranges: TrimRange[], duration: number): TrimRange[] {
  const gaps: TrimRange[] = []
  let cursor = 0
  for (const r of ranges) {
    if (r.start - cursor >= MIN_LENGTH) gaps.push({ start: cursor, end: r.start })
    cursor = r.end
  }
  if (duration - cursor >= MIN_LENGTH) gaps.push({ start: cursor, end: duration })
  return gaps
}

export function addRange(ranges: TrimRange[], playhead: number, duration: number): RangeAdd | null {
  const gaps = freeGaps(ranges, duration)
  const here = gaps.find((g) => playhead >= g.start && g.end - playhead >= MIN_LENGTH)
  const gap = here ?? gaps[0]
  if (!gap) return null
  const start = here ? playhead : gap.start
  const added = { start, end: gap.end }
  const next = [...ranges, added].sort((a, b) => a.start - b.start)
  return { ranges: next, index: next.indexOf(added) }
}

export function clampRangeAt(
  ranges: TrimRange[],
  index: number,
  handle: 'start' | 'end',
  value: number,
  duration: number,
): TrimRange[] {
  const floor = index > 0 ? ranges[index - 1].end : 0
  const ceiling = index < ranges.length - 1 ? ranges[index + 1].start : duration
  const current = ranges[index]
  const next =
    handle === 'start'
      ? { start: Math.min(Math.max(value, floor), current.end - MIN_LENGTH), end: current.end }
      : { start: current.start, end: Math.max(Math.min(value, ceiling), current.start + MIN_LENGTH) }
  return ranges.map((r, i) => (i === index ? next : r))
}

export function removeRange(ranges: TrimRange[], index: number): TrimRange[] {
  return ranges.filter((_, i) => i !== index)
}

export function splitSummary(ranges: TrimRange[], duration: number) {
  const kept = ranges.reduce((sum, r) => sum + (r.end - r.start), 0)
  return { count: ranges.length, kept, removed: duration - kept }
}
