import { gameHeadline, matchTypeLabel } from './games.ts'

interface CardClip {
  id: string
  title: string
  fileName?: string
  matchStartUtc?: string
  gameMode?: string
  matchResult?: unknown
}

type Result = Parameters<typeof gameHeadline>[0]

/** 클립 카드의 큰 글씨: 게임 정보(순위 · 일반/랭크)가 중심이고 파일 이름은 쓰지 않는다. */
export function cardHeadline(clip: CardClip): string {
  const result = (clip.matchResult ?? null) as Result
  const head = gameHeadline(result)
  const type = clip.gameMode === 'cobalt' ? '' : matchTypeLabel(result)
  return type ? `${head} · ${type}` : head
}

export function filterClips<T extends CardClip>(clips: T[], query: string): T[] {
  const q = query.trim().toLowerCase()
  if (!q) return clips
  return clips.filter((c) => `${c.title}\n${c.fileName ?? ''}`.toLowerCase().includes(q))
}

export function sortedForCategory<T extends CardClip>(clips: T[]): T[] {
  return [...clips].sort((a, b) => (b.matchStartUtc ?? '').localeCompare(a.matchStartUtc ?? ''))
}
