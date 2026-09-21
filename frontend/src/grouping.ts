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

  const byTime = (a: GameGroup<T>, b: GameGroup<T>) =>
    a.matchStartUtc < b.matchStartUtc ? -1 : a.matchStartUtc > b.matchStartUtc ? 1 : a.key < b.key ? -1 : 1
  const games = [...map.values()].sort(byTime)
  games.forEach((g, i) => {
    g.number = i + 1
    g.clips.sort(byId)
  })

  if (sort === 'desc') return games.reverse()
  if (sort === 'pvp') {
    const best = (g: GameGroup<T>) => Math.max(...g.clips.map((c) => c.pvpScore ?? -1))
    return games.sort((a, b) => best(b) - best(a) || byTime(a, b))
  }
  return games
}

export function formatMatchResult(result: MatchResult | null | undefined): string | null {
  if (!result) return null
  const parts = [`${result.placement}위`]
  if (result.matchType !== 'unknown') parts.unshift(result.matchType === 'rank' ? '랭크' : '일반')
  if (result.outcome?.includes('탈출')) parts.push(result.outcome)
  if (result.character) parts.unshift(result.character)
  return parts.join(' · ')
}

export function formatKda(result: MatchResult | null | undefined): string | null {
  if (!result || result.tk == null || result.kills == null || result.assists == null) return null
  return `${result.tk} / ${result.kills} / ${result.assists}`
}

export function formatAgo(iso: string, now: Date = new Date()): string {
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ''
  const minutes = Math.floor((now.getTime() - t) / 60000)
  if (minutes < 1) return '방금 전'
  if (minutes < 60) return `${minutes}분 전`
  if (minutes < 60 * 24) return `${Math.floor(minutes / 60)}시간 전`
  return `${Math.floor(minutes / 60 / 24)}일 전`
}

export function totalSize(clips: { sizeBytes?: number }[]): number {
  return clips.reduce((sum, c) => sum + (c.sizeBytes ?? 0), 0)
}

export function withResultImage<T extends Groupable>(groups: GameGroup<T>[]): GameGroup<T>[] {
  return groups.filter((g) => g.result?.imagePath)
}

export function formatTeammates(result: MatchResult | null | undefined): string | null {
  const names = (result?.teammates ?? []).map((t) => t.character ?? t.nickname)
  return names.length > 0 ? names.join(', ') : null
}
