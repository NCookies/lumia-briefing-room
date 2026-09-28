import type { GameRecord, MatchResult } from './types'

export type ClipSort = 'asc' | 'desc'

interface Groupable {
  id: string
  matchStartUtc?: string
  sessionDir?: string
  pvpScore: number | null
  matchResult?: MatchResult | null
  gameMode?: string | null
}

export interface GameGroup<T> {
  key: string
  number: number
  matchStartUtc: string
  result: MatchResult | null
  gameMode: string | null
  clips: T[]
  recordId?: string
  startSec?: number
  endSec?: number
}

export type ResultImageRef =
  | { kind: 'record'; id: string }
  | { kind: 'clip'; id: string }
  | { kind: 'vodGame'; vodId: string; index: number }

/**
 * 결과 화면 이미지를 어떤 API 로 찾을지 정한다. 클립이 없는 VOD 게임(코발트처럼 교전은
 * 못 뽑았어도 결과 화면은 읽은 경우, plan.md §10-6)엔 `clips[0]` 이 없다 - 이 분기를
 * 호출부마다 따로 적다가 두 번이나 `clips[0].id` 로 죽였다(실사용 보고, 2026-09-27).
 * VOD 그룹의 key 는 항상 `${vodId}|${index}` 다(vodGrouping.ts).
 */
export function resultImageRef(group: { recordId?: string; clips: { id: string }[]; key: string; number: number }): ResultImageRef {
  if (group.recordId) return { kind: 'record', id: group.recordId }
  if (group.clips[0]) return { kind: 'clip', id: group.clips[0].id }
  return { kind: 'vodGame', vodId: group.key.split('|')[0], index: group.number }
}

const byId = (a: { id: string }, b: { id: string }) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)

export const gameRecordId = (sessionDir: string | null | undefined, matchStartUtc: string | null | undefined): string =>
  `${sessionDir ?? ''}__${matchStartUtc ?? ''}`.replace(/[^0-9A-Za-z._-]/g, '_')

export function groupByGame<T extends Groupable>(
  clips: T[],
  sort: ClipSort,
  records: GameRecord[] = [],
): GameGroup<T>[] {
  const map = new Map<string, GameGroup<T>>()
  for (const clip of clips) {
    const key = `${clip.sessionDir ?? ''}|${clip.matchStartUtc ?? ''}`
    const group = map.get(key)
    if (group) {
      group.clips.push(clip)
      group.result ??= clip.matchResult ?? null
      group.gameMode ??= clip.gameMode ?? null
    } else {
      map.set(key, {
        key,
        number: 0,
        matchStartUtc: clip.matchStartUtc ?? '',
        result: clip.matchResult ?? null,
        gameMode: clip.gameMode ?? null,
        clips: [clip],
      })
    }
  }

  for (const record of records) {
    const key = `${record.sessionDir ?? ''}|${record.matchStartUtc}`
    if (map.has(key)) continue
    map.set(key, {
      key,
      number: 0,
      matchStartUtc: record.matchStartUtc,
      result: record.matchResult,
      gameMode: record.gameMode ?? null,
      clips: [],
      recordId: record.id,
    })
  }

  const byTime = (a: GameGroup<T>, b: GameGroup<T>) =>
    a.matchStartUtc < b.matchStartUtc ? -1 : a.matchStartUtc > b.matchStartUtc ? 1 : a.key < b.key ? -1 : 1
  const games = [...map.values()].sort(byTime)
  games.forEach((g, i) => {
    g.number = i + 1
    g.clips.sort(byId)
  })

  if (sort === 'desc') return games.reverse()
  return games
}

export const COBALT_OUTCOMES = ['승리', '패배'] as const

export function formatMatchResult(result: MatchResult | null | undefined): string | null {
  if (!result) return null
  // 코발트 프로토콜은 순위가 아니라 승/패다(§10 C3) - matchType/placement 대신 승패 글자를 쓴다.
  if (result.outcome && (COBALT_OUTCOMES as readonly string[]).includes(result.outcome)) {
    return result.character ? `${result.character} · ${result.outcome}` : result.outcome
  }
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
  const names = (result?.teammates ?? []).map((t) => t.character ?? '미확인')
  return names.length > 0 ? names.join(', ') : null
}
