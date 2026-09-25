import type { ClipSort, GameGroup } from './grouping'
import type { MatchResult } from './types'

export type VodStatus = 'new' | 'analyzing' | 'interrupted' | 'cancelled' | 'error' | 'done'

export interface VodGameSummary {
  index: number
  startSec: number
  endSec: number
  confidence?: number
  kFinal?: number | null
  aFinal?: number | null
  result: MatchResult | null
  clipIds: string[]
}

export interface Vod {
  id: string
  path: string
  name: string
  exists: boolean
  sizeBytes: number | null
  durationSec: number | null
  width: number | null
  height: number | null
  status: VodStatus
  analyzedSec: number | null
  error: string | null
  streamer: string | null
  games: VodGameSummary[]
  clipCount: number
  clipBytes: number
  trashedCount: number
}

export interface VodClipLike {
  id: string
  vodId?: string
  vodGameIndex?: number
  gameStartOffsetSec?: number
  gameEndOffsetSec?: number
  pvpScore: number | null
  matchResult?: MatchResult | null
}

export interface VodGroup<T> {
  vodId: string
  name: string
  vod: Vod | null
  games: GameGroup<T>[]
}

const byId = (a: { id: string }, b: { id: string }) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)

export function groupByVod<T extends VodClipLike>(
  clips: T[],
  vods: Vod[],
  sort: ClipSort,
  includeEmpty: boolean,
): VodGroup<T>[] {
  const known = new Map(vods.map((v) => [v.id, v]))
  const games = new Map<string, Map<number, GameGroup<T>>>()

  for (const clip of clips) {
    if (!clip.vodId) continue
    const perVod = games.get(clip.vodId) ?? new Map<number, GameGroup<T>>()
    games.set(clip.vodId, perVod)
    const index = clip.vodGameIndex ?? 0
    const existing = perVod.get(index)
    if (existing) {
      existing.clips.push(clip)
      existing.result ??= clip.matchResult ?? null
    } else {
      perVod.set(index, {
        key: `${clip.vodId}|${index}`,
        number: index,
        matchStartUtc: '',
        result: clip.matchResult ?? null,
        clips: [clip],
        startSec: clip.gameStartOffsetSec,
        endSec: clip.gameEndOffsetSec,
      })
    }
  }

  const keptEmpty = includeEmpty ? vods.filter((v) => !(v.status === 'done' && v.clipCount === 0)).map((v) => v.id) : []
  const ids = new Set<string>([...games.keys(), ...keptEmpty])
  const groups: VodGroup<T>[] = [...ids].map((vodId) => {
    const vod = known.get(vodId) ?? null
    const list = [...(games.get(vodId)?.values() ?? [])]
    for (const g of list) g.clips.sort(byId)
    list.sort((a, b) => a.number - b.number)
    if (sort === 'desc') list.reverse()
    if (sort === 'pvp') {
      const best = (g: GameGroup<T>) => Math.max(...g.clips.map((c) => c.pvpScore ?? -1))
      list.sort((a, b) => best(b) - best(a) || a.number - b.number)
    }
    return { vodId, name: vod?.name ?? vodId, vod, games: list }
  })

  return groups.sort((a, b) => a.name.localeCompare(b.name, 'ko', { sensitivity: 'base' }))
}

export function formatDuration(sec: number | null | undefined): string {
  if (sec == null) return ''
  const total = Math.max(0, Math.floor(sec))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`
}

export function formatGameRange(startSec: number, endSec: number): string {
  const full = (sec: number) => {
    const total = Math.floor(sec)
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${Math.floor(total / 3600)}:${pad(Math.floor((total % 3600) / 60))}:${pad(total % 60)}`
  }
  return `${full(startSec)} ~ ${full(endSec)}`
}

const STATUS_LABELS: Record<VodStatus, string> = {
  new: '분석 안 함',
  analyzing: '분석 중',
  interrupted: '분석 중단됨',
  cancelled: '분석 취소됨',
  error: '분석 실패',
  done: '분석 완료',
}

export function vodStatusLabel(status: VodStatus): string {
  return STATUS_LABELS[status]
}

export function analysisPercent(vod: Pick<Vod, 'analyzedSec' | 'durationSec'>): number {
  if (!vod.analyzedSec || !vod.durationSec) return 0
  return Math.min(100, Math.round((vod.analyzedSec / vod.durationSec) * 100))
}
