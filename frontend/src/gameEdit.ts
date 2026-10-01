import type { MatchResult } from './games.ts'
import { vodGameHeading } from './vodGames.ts'

export const TITLE_MAX = 60
const PLACEMENT_MAX = 99
const COUNT_MAX = 999

export interface GameEditDraft {
  placement: string
  matchType: 'rank' | 'normal' | 'unknown'
  outcome: string
  tk: string
  kills: string
  assists: string
}

export interface GameEditPatch {
  placement?: number | null
  matchType?: 'rank' | 'normal' | 'unknown'
  outcome?: string | null
  tk?: number | null
  kills?: number | null
  assists?: number | null
}

const text = (v: number | null | undefined) => (v == null ? '' : String(v))

export function draftOf(result: MatchResult | null): GameEditDraft {
  return {
    placement: text(result?.placement),
    matchType: result?.matchType ?? 'unknown',
    outcome: result?.outcome ?? '',
    tk: text(result?.tk),
    kills: text(result?.kills),
    assists: text(result?.assists),
  }
}

function whole(value: string, min: number, max: number): number | null | undefined {
  const trimmed = value.trim()
  if (trimmed === '') return null
  if (!/^\d+$/.test(trimmed)) return undefined
  const n = Number(trimmed)
  return n >= min && n <= max ? n : undefined
}

export type ParsedDraft = { ok: true; patch: GameEditPatch } | { ok: false; error: string }

/** 입력 칸을 서버로 보낼 값으로 바꾼다. 빈 칸은 null(값 비움). 코발트는 순위·일반/랭크 대신 승리/패배를 보낸다. */
export function parseDraft(draft: GameEditDraft, cobalt: boolean): ParsedDraft {
  const patch: GameEditPatch = {}
  if (cobalt) {
    patch.outcome = draft.outcome === '' ? null : draft.outcome
  } else {
    const placement = whole(draft.placement, 1, PLACEMENT_MAX)
    if (placement === undefined) return { ok: false, error: `순위는 1~${PLACEMENT_MAX} 사이의 정수로 입력하세요` }
    patch.placement = placement
    patch.matchType = draft.matchType
  }
  for (const [field, label] of [['tk', 'TK'], ['kills', 'K'], ['assists', 'A']] as const) {
    const value = whole(draft[field], 0, COUNT_MAX)
    if (value === undefined) return { ok: false, error: `${label} 는 0 이상의 정수로 입력하세요` }
    patch[field] = value
  }
  return { ok: true, patch }
}

/** 제목 입력값: 앞뒤 공백을 지우고, 비면 null(제목 없음), 길면 자른다. */
export function titleValue(input: string): string | null {
  const trimmed = input.trim().slice(0, TITLE_MAX)
  return trimmed === '' ? null : trimmed
}

/** 풀영상 화면 머리줄 글자: 사용자 제목이 있으면 그것, 없으면 영상 게임은 `스트리머 · 게임 N`, 스팀 게임은 경기 키. */
export function gameHeading(g: {
  gameKey: string
  title?: string | null
  source?: 'steam' | 'vod'
  streamer?: string | null
  vodGameIndex?: number | null
}): string {
  if (g.title) return g.title
  return g.source === 'vod' ? vodGameHeading(g) : g.gameKey
}
