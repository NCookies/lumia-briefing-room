export interface PhaseClip {
  phaseIndex: number | null
}

export interface PhaseColumn<T> {
  phaseIndex: number | null
  label: string
  zone: 'free' | 'credit' | null
  clips: T[]
}

export const LAST_FREE_PHASE = 3

export function phaseLabel(phaseIndex: number): string {
  return `${Math.floor(phaseIndex / 2) + 1}일차 ${phaseIndex % 2 === 0 ? '낮' : '밤'}`
}

export function buildPhaseColumns<T extends PhaseClip>(clips: T[]): PhaseColumn<T>[] {
  const known = clips.filter((c) => c.phaseIndex !== null)
  const columns: PhaseColumn<T>[] = []
  if (known.length > 0) {
    const last = Math.max(...known.map((c) => c.phaseIndex as number))
    for (let p = 0; p <= last; p++) {
      columns.push({
        phaseIndex: p,
        label: phaseLabel(p),
        zone: p <= LAST_FREE_PHASE ? 'free' : 'credit',
        clips: known.filter((c) => c.phaseIndex === p),
      })
    }
  }
  const unknown = clips.filter((c) => c.phaseIndex === null)
  if (unknown.length > 0) columns.push({ phaseIndex: null, label: '시점 알 수 없음', zone: null, clips: unknown })
  return columns
}
