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
