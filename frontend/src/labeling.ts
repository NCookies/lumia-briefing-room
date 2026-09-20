import type { UserLabel } from './types'

export type ScoreTone = 'confirmed' | 'likely' | 'weak' | 'none'

export function labelForKey(key: string): UserLabel | undefined {
  if (key === '1') return 'pvp'
  if (key === '2') return 'pve'
  if (key === '0' || key === 'Backspace' || key === 'Delete') return null
  return undefined
}

export function applyLabel<T extends { id: string; userLabel: UserLabel }>(
  clips: T[],
  id: string,
  label: UserLabel,
): T[] {
  return clips.map((c) => (c.id === id ? { ...c, userLabel: label } : c))
}

export function nextUnlabeledIndex(clips: { userLabel: UserLabel }[], from: number): number | null {
  for (let step = 1; step <= clips.length; step++) {
    const i = (from + step) % clips.length
    if (clips[i].userLabel === null) return i
  }
  return null
}

export function progress(clips: { userLabel: UserLabel }[]): { labeled: number; total: number } {
  return { labeled: clips.filter((c) => c.userLabel !== null).length, total: clips.length }
}

export function scorePercent(score: number | null | undefined): string {
  return score == null ? '-' : `${Math.round(score * 100)}%`
}

export function scoreTone(score: number | null | undefined): ScoreTone {
  if (score == null || score <= 0) return 'none'
  if (score >= 1) return 'confirmed'
  return score >= 0.4 ? 'likely' : 'weak'
}
