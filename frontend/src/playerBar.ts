import { MIN_RANGE_SEC, effectiveRange, isDismissed, isSaved, type Candidate } from './games.ts'

export type View = [number, number]

const ZOOM_PAD_SEC = 30
const NEW_RANGE_PAD_SEC = 10
const TICK_STEPS = [5, 10, 30, 60, 120, 300, 600, 1800]
const MAX_TICKS = 10
const MIN_VIEW_SEC = 10

export function barPct(t: number, view: View): number {
  const span = view[1] - view[0]
  if (span <= 0) return 0
  return Math.min(100, Math.max(0, ((t - view[0]) / span) * 100))
}

export function timeFromBar(clientX: number, left: number, width: number, view: View): number {
  if (width <= 0) return 0
  const ratio = Math.min(1, Math.max(0, (clientX - left) / width))
  return view[0] + ratio * (view[1] - view[0])
}

/** 확대: 선택한 후보 앞뒤 30초를 막대 전체 폭으로. */
export function zoomView(range: [number, number], duration: number): View {
  return [Math.max(0, range[0] - ZOOM_PAD_SEC), Math.min(duration, range[1] + ZOOM_PAD_SEC)]
}

/** 확대한 범위를 좌우로 옮긴다. 폭은 그대로, 영상 밖으로는 나가지 않는다. */
export function panView(view: View, deltaSec: number, duration: number): View {
  const span = view[1] - view[0]
  const start = Math.min(Math.max(0, view[0] + deltaSec), Math.max(0, duration - span))
  return [start, start + span]
}

/** 그 시각이 든 후보(무시한 후보 제외). 겹치면 더 짧은 구간이 이긴다. */
export function candidateAtTime(cands: Candidate[], t: number, duration: number): Candidate | null {
  let best: { c: Candidate; length: number } | null = null
  for (const c of cands) {
    if (isDismissed(c)) continue
    const [s, e] = effectiveRange(c, duration)
    if (t < s || t > e) continue
    if (!best || e - s < best.length) best = { c, length: e - s }
  }
  return best?.c ?? null
}

export function candidateAtBar(
  cands: Candidate[],
  clientX: number,
  left: number,
  width: number,
  view: View,
  duration: number,
): Candidate | null {
  return candidateAtTime(cands, timeFromBar(clientX, left, width, view), duration)
}

/** I/O: 시작점·끝점을 현재 위치로. 시작 > 끝이 되지 않게 최소 길이를 지킨다. */
export function applyMark(kind: 'start' | 'end', range: [number, number], now: number, duration: number): [number, number] {
  const [start, end] = range
  if (kind === 'start') return [Math.max(0, Math.min(now, end - MIN_RANGE_SEC)), end]
  return [start, Math.min(duration, Math.max(now, start + MIN_RANGE_SEC))]
}

/** "+ 여기서 구간 추가": 현재 위치 앞뒤 10초. */
export function newRangeAround(now: number, duration: number): [number, number] {
  return [Math.max(0, now - NEW_RANGE_PAD_SEC), Math.min(duration, now + NEW_RANGE_PAD_SEC)]
}

export function tickStep(span: number): number {
  return TICK_STEPS.find((s) => span / s <= MAX_TICKS) ?? TICK_STEPS[TICK_STEPS.length - 1]
}

/** 돋보기 +/-: 보이는 범위를 factor 배로 바꾼다(중심 유지). 전체가 다 보이게 되면 null(전체 보기). */
export function zoomBy(view: View, factor: number, center: number, duration: number): View | null {
  const span = Math.min(duration, Math.max(MIN_VIEW_SEC, (view[1] - view[0]) * factor))
  if (span >= duration * 0.999) return null
  const ratio = (center - view[0]) / (view[1] - view[0])
  const start = Math.min(Math.max(0, center - ratio * span), duration - span)
  return [start, start + span]
}

/** 저장한 뒤(또는 저장한 적 없으면 검출된 값에서) 범위를 고쳤는가. */
export function rangeModified(c: Candidate, duration: number): boolean {
  const [s, e] = effectiveRange(c, duration)
  const u = c.user
  const [bs, be] =
    isSaved(c) && u.savedStart !== undefined && u.savedEnd !== undefined
      ? [u.savedStart, u.savedEnd]
      : [Math.max(0, c.start), duration > 0 ? Math.min(duration, c.end) : c.end]
  return Math.abs(s - bs) > 0.001 || Math.abs(e - be) > 0.001
}
