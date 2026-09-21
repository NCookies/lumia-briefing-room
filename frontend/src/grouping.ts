import type { MatchResult } from './types'

export type ClipSort = 'asc' | 'desc' | 'pvp'

interface Groupable {
  id: string
  matchStartUtc: string
  sessionDir: string
  pvpScore: number | null
  matchResult?: MatchResult | null
}

export interface GameGroup<T> {
  key: string
  number: number
  matchStartUtc: string
  result: MatchResult | null
  clips: T[]
}

const byId = (a: { id: string }, b: { id: string }) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)

export function groupByGame<T extends Groupable>(clips: T[], sort: ClipSort): GameGroup<T>[] {
  const map = new Map<string, GameGroup<T>>()
  for (const clip of clips) {
    const key = `${clip.sessionDir}|${clip.matchStartUtc}`
    const group = map.get(key)
    if (group) {
      group.clips.push(clip)
      group.result ??= clip.matchResult ?? null
    } else {
      map.set(key, {
        key,
        number: 0,
        matchStartUtc: clip.matchStartUtc,
        result: clip.matchResult ?? null,
        clips: [clip],
      })
    }
  }

  const games = [...map.values()].sort((a, b) =>
    a.matchStartUtc < b.matchStartUtc ? -1 : a.matchStartUtc > b.matchStartUtc ? 1 : a.key < b.key ? -1 : 1,
  )
  games.forEach((g, i) => {
    g.number = i + 1
    if (sort === 'pvp') g.clips.sort((a, b) => (b.pvpScore ?? -1) - (a.pvpScore ?? -1))
    else g.clips.sort(byId)
    if (sort === 'desc') g.clips.reverse()
  })
  if (sort === 'desc') games.reverse()
  return games
}

export function formatMatchResult(result: MatchResult | null | undefined): string | null {
  if (!result) return null
  const parts = [result.matchType === 'rank' ? '랭크' : '일반', `${result.placement}위 / ${result.total}팀`]
  if (result.outcome) parts.push(result.outcome)
  return parts.join(' · ')
}
