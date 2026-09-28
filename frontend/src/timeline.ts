export interface PhaseClip {
  phaseIndex: number | null
  elapsedGameSec?: number | null
}

export interface PhaseColumnEntry<T> {
  clip: T
  estimated: boolean
}

export interface PhaseColumn<T> {
  phaseIndex: number | null
  label: string
  zone: 'free' | 'credit' | null
  clips: PhaseColumnEntry<T>[]
}

export const LAST_FREE_PHASE = 3

/** 한 페이즈(낮 또는 밤) 길이. SPEC §2.10 실측값("대략 2.5~3분")의 중간값(2분 45초). */
export const PHASE_LENGTH_SEC = 165

export function phaseLabel(phaseIndex: number): string {
  return `${Math.floor(phaseIndex / 2) + 1}일차 ${phaseIndex % 2 === 0 ? '낮' : '밤'}`
}

/** 게임 경과 시간(초)을 페이즈 길이로 나눠 페이즈 순번을 추정한다. 음수는 0으로 자른다. */
export function estimatePhaseIndex(elapsedGameSec: number, phaseLengthSec: number = PHASE_LENGTH_SEC): number {
  return Math.max(0, Math.floor(elapsedGameSec / phaseLengthSec))
}

export interface TimeableClip {
  source?: 'steam' | 'vod'
  sessionStartUtc?: string
  matchStartUtc?: string
  combatStartOffsetSec?: number
  gameStartOffsetSec?: number
}

/** 클립 교전 시작 시각 − 게임 시작 시각(초). 계산에 필요한 값이 없거나 음수면 null(계산 불가). */
export function elapsedGameSec(clip: TimeableClip): number | null {
  if (clip.combatStartOffsetSec === undefined) return null
  if (clip.source === 'vod') {
    if (clip.gameStartOffsetSec === undefined) return null
    const elapsed = clip.combatStartOffsetSec - clip.gameStartOffsetSec
    return elapsed >= 0 ? elapsed : null
  }
  if (!clip.sessionStartUtc || !clip.matchStartUtc) return null
  const sessionStartMs = Date.parse(clip.sessionStartUtc)
  const matchStartMs = Date.parse(clip.matchStartUtc)
  if (Number.isNaN(sessionStartMs) || Number.isNaN(matchStartMs)) return null
  const combatAbsoluteMs = sessionStartMs + clip.combatStartOffsetSec * 1000
  const elapsed = (combatAbsoluteMs - matchStartMs) / 1000
  return elapsed >= 0 ? elapsed : null
}

export function buildPhaseColumns<T extends PhaseClip>(
  clips: T[],
  phaseLengthSec: number = PHASE_LENGTH_SEC,
): PhaseColumn<T>[] {
  const placed: { clip: T; phase: number; estimated: boolean }[] = []
  const trulyUnknown: T[] = []

  for (const clip of clips) {
    if (clip.phaseIndex !== null) {
      placed.push({ clip, phase: clip.phaseIndex, estimated: false })
      continue
    }
    const elapsed = clip.elapsedGameSec
    if (elapsed != null && Number.isFinite(elapsed)) {
      placed.push({ clip, phase: estimatePhaseIndex(elapsed, phaseLengthSec), estimated: true })
    } else {
      trulyUnknown.push(clip)
    }
  }

  const columns: PhaseColumn<T>[] = []
  if (placed.length > 0) {
    const last = Math.max(...placed.map((e) => e.phase))
    for (let p = 0; p <= last; p++) {
      columns.push({
        phaseIndex: p,
        label: phaseLabel(p),
        zone: p <= LAST_FREE_PHASE ? 'free' : 'credit',
        clips: placed.filter((e) => e.phase === p).map(({ clip, estimated }) => ({ clip, estimated })),
      })
    }
  }
  if (trulyUnknown.length > 0) {
    columns.push({
      phaseIndex: null,
      label: '시점 알 수 없음',
      zone: null,
      clips: trulyUnknown.map((clip) => ({ clip, estimated: false })),
    })
  }
  return columns
}
