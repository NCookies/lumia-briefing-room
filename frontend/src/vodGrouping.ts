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
  gameMode?: string | null
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
  videoDate: string | null
  games: VodGameSummary[]
  clipCount: number
  clipBytes: number
  probing: boolean
}

export interface VodClipLike {
  id: string
  vodId?: string
  vodGameIndex?: number
  gameStartOffsetSec?: number
  gameEndOffsetSec?: number
  pvpScore: number | null
  matchResult?: MatchResult | null
  gameMode?: string | null
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
      existing.gameMode ??= clip.gameMode ?? null
    } else {
      perVod.set(index, {
        key: `${clip.vodId}|${index}`,
        number: index,
        matchStartUtc: '',
        result: clip.matchResult ?? null,
        gameMode: clip.gameMode ?? null,
        clips: [clip],
        startSec: clip.gameStartOffsetSec,
        endSec: clip.gameEndOffsetSec,
      })
    }
  }

  // 클립이 0개인 게임도 결과(승패·스탯·팀원)는 이미 다 읽어 뒀을 수 있다(예: 코발트
  // 다시보기가 오버레이 때문에 교전은 못 뽑아도 결과 화면은 읽는 경우, plan.md §10-6
  // 실사용 보고 - "게임 6개인데 화면엔 아무것도 안 뜬다"). 클립에서만 게임 행을 만들면
  // 이런 결과가 통째로 안 보이므로, `vod.games` 요약에서 클립이 없는 게임도 행으로 만든다.
  if (includeEmpty) {
    for (const vod of vods) {
      const perVod = games.get(vod.id) ?? new Map<number, GameGroup<T>>()
      games.set(vod.id, perVod)
      for (const g of vod.games) {
        if (perVod.has(g.index)) continue
        perVod.set(g.index, {
          key: `${vod.id}|${g.index}`,
          number: g.index,
          matchStartUtc: '',
          result: g.result,
          gameMode: g.gameMode ?? null,
          clips: [],
          startSec: g.startSec,
          endSec: g.endSec,
        })
      }
    }
  }

  // 클립이 0개인 이유(게임을 못 찾음 / 게임은 찾았지만 클립을 지움)를 구분해서
  // 숨기려다 보니 조건이 복잡해지고, 그 조건에 걸리면 "다시 분석" 버튼도 같이
  // 사라져 되돌릴 방법이 없었다(실사용 보고, 2026-09-27). 숨기지 않는다 — 보기
  // 싫은 항목은 사용자가 직접 지운다(영상 삭제). 대신 목록은 새로고침 버튼으로
  // 언제든 다시 읽는다(`ClipBrowser.tsx`).
  const keptEmpty = includeEmpty ? vods.map((v) => v.id) : []
  const ids = new Set<string>([...games.keys(), ...keptEmpty])
  const groups: VodGroup<T>[] = [...ids].map((vodId) => {
    const vod = known.get(vodId) ?? null
    const list = [...(games.get(vodId)?.values() ?? [])]
    for (const g of list) g.clips.sort(byId)
    list.sort((a, b) => a.number - b.number)
    if (sort === 'desc') list.reverse()
    return { vodId, name: vod?.name ?? vodId, vod, games: list }
  })

  return groups.sort((a, b) => a.name.localeCompare(b.name, 'ko', { sensitivity: 'base' }))
}

export interface ProbeProgress {
  total: number
  pending: number
  done: number
  percent: number
  active: boolean
}

export function probeProgress(vods: Pick<Vod, 'probing'>[]): ProbeProgress {
  const total = vods.length
  const pending = vods.filter((v) => v.probing).length
  const done = total - pending
  return { total, pending, done, percent: total === 0 ? 100 : Math.floor((done / total) * 100), active: pending > 0 }
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

export function analysisBlockedReason(vod: Pick<Vod, 'exists'> | null, analysisBusy: boolean): string {
  if (vod === null) return ''
  if (!vod.exists) return '영상 파일을 찾을 수 없어 분석할 수 없습니다'
  if (analysisBusy) return '다른 영상을 분석하는 중입니다. 끝나면 시작할 수 있습니다'
  return ''
}
