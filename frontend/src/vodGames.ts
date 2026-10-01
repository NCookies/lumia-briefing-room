import type { GameDetail, GameSummary } from './games.ts'
import { allCandidates } from './games.ts'
import { formatGameRange, type Vod } from './vodGrouping.ts'

export interface VodGameGroup {
  vodId: string
  name: string
  vod: Vod | null
  games: GameSummary[]
}

/** 영상마다 그 영상의 게임(게임 번호 순). 게임이 없는 영상도 만든다(분석을 시작해야 하므로). 영상 목록에서 사라진 영상의 게임은 영상 id 로 보인다. 영상은 이름순. */
export function groupGamesByVod(vods: Vod[], games: GameSummary[]): VodGameGroup[] {
  const byVod = new Map<string, GameSummary[]>()
  for (const g of games) {
    if (!g.vodId) continue
    byVod.set(g.vodId, [...(byVod.get(g.vodId) ?? []), g])
  }
  const known = new Map(vods.map((v) => [v.id, v]))
  const ids = new Set([...known.keys(), ...byVod.keys()])
  return [...ids]
    .map((vodId) => {
      const vod = known.get(vodId) ?? null
      const list = [...(byVod.get(vodId) ?? [])].sort((a, b) => (a.gameIndex ?? 0) - (b.gameIndex ?? 0))
      return { vodId, name: vod?.name ?? vodId, vod, games: list }
    })
    .sort((a, b) => a.name.localeCompare(b.name, 'ko', { sensitivity: 'base' }))
}

/** 풀영상이 없어 "풀영상 만들기"가 필요한 옛 게임 수. 자동 정리로 지운 풀영상은 다시 만들지 않는다. */
export function buildableGameCount(games: Pick<GameSummary, 'legacy' | 'hasFullVideo' | 'fullVideoDeletedAt'>[]): number {
  return games.filter((g) => g.legacy && !g.hasFullVideo && !g.fullVideoDeletedAt).length
}

export function vodTotals(games: Pick<GameSummary, 'savedClipCount' | 'fullVideoSizeBytes'>[]): {
  games: number
  clips: number
  bytes: number
} {
  return {
    games: games.length,
    clips: games.reduce((n, g) => n + g.savedClipCount, 0),
    bytes: games.reduce((n, g) => n + (g.fullVideoSizeBytes ?? 0), 0),
  }
}

/** 게임 행의 시간 칸: 게임 번호와 원본 영상 안 위치(선택 화면 ~ 결과 화면). */
export function vodGameTime(g: Pick<GameSummary, 'gameIndex' | 'vodStartSec' | 'vodEndSec'>): { main: string; sub: string } {
  const sub = g.vodStartSec != null && g.vodEndSec != null ? formatGameRange(g.vodStartSec, g.vodEndSec) : ''
  return { main: `게임 ${g.gameIndex ?? ''}`.trim(), sub }
}

export function vodGameHeading(g: { streamer?: string | null; vodGameIndex?: number | null }): string {
  const game = `게임 ${g.vodGameIndex ?? ''}`.trim()
  return g.streamer ? `${g.streamer} · ${game}` : game
}

export interface SavedClipRef {
  id: string
  title: string
  durationSec: number
}

/** 풀영상이 없는 옛 영상 게임의 저장된 클립. 게임 기록의 후보(저장됨)에서 온다 — 영상 클립은 스팀 클립 목록에 없다. */
export function clipsOfVodGame(game: Pick<GameDetail, 'candidates' | 'userCandidates'>): SavedClipRef[] {
  return allCandidates(game)
    .filter((c) => c.user.savedClipId)
    .sort((a, b) => (a.user.start ?? a.start) - (b.user.start ?? b.start))
    .map((c) => ({
      id: c.user.savedClipId as string,
      title: c.user.title || c.title,
      durationSec: (c.user.end ?? c.end) - (c.user.start ?? c.start),
    }))
}

/** 분석 중이던 영상이 더 이상 분석 중이 아니게 된 순간. 서버는 영상 색인을 "완료"로 먼저 쓰고 작업 상태는 조금 뒤에 바꾼다 -
 * 작업 상태만 보면 그 틈에 타이머가 꺼져 게임 목록을 다시 읽지 않았다(2026-10-01). */
export function analysisEnded(previous: string | null, current: string | null): boolean {
  return previous !== null && previous !== current
}
