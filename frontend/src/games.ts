export interface CandidateUser {
  start?: number
  end?: number
  dismissed?: boolean
  label?: 'combat' | 'hunt'
  title?: string
  savedClipId?: string
  savedCategory?: string
  /** 자동 보관이 아닌 카테고리에 있는 클립일 때만 true(계산 값). 자동 보관의 클립은 파일은 있어도 보관된 것이 아니다. */
  archived?: boolean
  savedMemo?: string
  savedStart?: number
  savedEnd?: number
}

export interface Candidate {
  id: string
  start: number
  end: number
  combatStart?: number
  combatEnd?: number
  title: string
  tags: string[]
  certain: boolean
  pvpScore?: number
  region?: string | null
  gameDay?: number | null
  dayNight?: string | null
  user: CandidateUser
}

export interface Marker {
  t: number
  kind: 'kill' | 'assist' | 'death' | 'teammate_death'
}

export interface MatchResult {
  placement?: number | null
  total?: number | null
  outcome?: string
  kills?: number
  deaths?: number
  assists?: number
  tk?: number
  matchLabel?: string
  matchType?: 'rank' | 'normal' | 'unknown'
}

export interface GameSummary {
  key: string
  source?: 'steam' | 'vod'
  vodId?: string | null
  gameIndex?: number | null
  streamer?: string | null
  vodStartSec?: number | null
  vodEndSec?: number | null
  matchStartUtc: string | null
  matchEndUtc: string | null
  gameMode: string | null
  matchResult: MatchResult | null
  /** `manual` 이면 사용자가 고친 값이라 다시 분석·소급 채우기가 덮어쓰지 않는다. */
  matchResultSource?: 'manual' | null
  title?: string | null
  portraits: Record<string, string | null>
  pinned: boolean
  sourceIncomplete: boolean
  hasFullVideo: boolean
  fullVideoSizeBytes: number | null
  durationSec: number | null
  fullVideoError: string | null
  recordingStopped?: RecordingStopped
  fullVideoDeletedAt: string | null
  legacy: boolean
  canRebuildFullVideo?: boolean
  candidateCount: number
  certainCount: number
  savedClipCount: number
  autoClipCount: number
  unsavedEditCount: number
}

export interface GameDetail {
  gameKey: string
  source?: 'steam' | 'vod'
  vodId?: string | null
  vodGameIndex?: number | null
  streamer?: string | null
  matchStartUtc: string | null
  sessionDir?: string | null
  legacy?: boolean
  canRebuildFullVideo?: boolean
  hasFullVideo: boolean
  fullVideo: { durationSec: number; sizeBytes: number | null } | null
  fullVideoError: string | null
  recordingStopped?: RecordingStopped
  candidates: Candidate[]
  userCandidates: Candidate[]
  markers: Marker[]
  matchResult: MatchResult | null
  matchResultSource?: 'manual' | null
  title?: string | null
  gameMode?: string | null
  pinned: boolean
}

export const MIN_RANGE_SEC = 1

export function allCandidates(game: Pick<GameDetail, 'candidates' | 'userCandidates'>): Candidate[] {
  return [...game.candidates, ...game.userCandidates]
}

export function isDismissed(c: Candidate): boolean {
  return c.user.dismissed === true
}

export function isSaved(c: Candidate): boolean {
  return Boolean(c.user.savedClipId)
}

export function effectiveRange(c: Candidate, duration: number): [number, number] {
  const start = c.user.start ?? c.start
  const end = c.user.end ?? c.end
  return [Math.max(0, start), duration > 0 ? Math.min(duration, end) : end]
}

export function visibleCandidates(game: Pick<GameDetail, 'candidates' | 'userCandidates'>, showDismissed = false): Candidate[] {
  return allCandidates(game)
    .filter((c) => showDismissed || !isDismissed(c))
    .sort((a, b) => (a.user.start ?? a.start) - (b.user.start ?? b.start))
}

export function positionPct(t: number, duration: number): number {
  if (duration <= 0) return 0
  return Math.min(100, Math.max(0, (t / duration) * 100))
}

export function timeFromPointer(clientX: number, left: number, width: number, duration: number): number {
  if (width <= 0) return 0
  const ratio = Math.min(1, Math.max(0, (clientX - left) / width))
  return ratio * duration
}

const EPS = 0.5

/** 이전/다음 후보의 시작 시각. `certainOnly` 면 킬·어시·사망이 있는 후보만 건너뛴다. */
export function neighborCandidate(
  cands: Candidate[],
  now: number,
  direction: 'prev' | 'next',
  duration: number,
  certainOnly = false,
): Candidate | null {
  const pool = cands
    .filter((c) => !isDismissed(c) && (!certainOnly || c.certain))
    .map((c) => ({ c, start: effectiveRange(c, duration)[0] }))
    .sort((a, b) => a.start - b.start)
  if (direction === 'next') return pool.find((p) => p.start > now + EPS)?.c ?? null
  return [...pool].reverse().find((p) => p.start < now - EPS)?.c ?? null
}

export type DragKind = 'start' | 'end' | 'move'

/** 핸들을 끌어 범위를 바꾼다. 영상 밖으로 나가지 않고 최소 길이를 지킨다. */
export function dragRange(
  kind: DragKind,
  range: [number, number],
  deltaSec: number,
  duration: number,
): [number, number] {
  const [start, end] = range
  if (kind === 'start') return [Math.min(Math.max(0, start + deltaSec), end - MIN_RANGE_SEC), end]
  if (kind === 'end') return [start, Math.max(Math.min(duration, end + deltaSec), start + MIN_RANGE_SEC)]
  const length = end - start
  const moved = Math.min(Math.max(0, start + deltaSec), Math.max(0, duration - length))
  return [moved, moved + length]
}

/** 게임 행의 개수 표시. "클립 N개"만 두면 직접 보관 모드에서 후보가 잔뜩 있어도 0개로 보여 헷갈렸다(2026-10-01). */
export function clipCountsLabel(g: Pick<GameSummary, 'candidateCount' | 'savedClipCount'>): string {
  return `후보 ${g.candidateCount} · 보관 ${g.savedClipCount}`
}

export function formatClock(sec: number): string {
  const total = Math.max(0, Math.floor(sec))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${ss}` : `${m}:${ss}`
}

export const MARKER_LABEL: Record<Marker['kind'], string> = {
  kill: '킬',
  assist: '어시스트',
  death: '사망',
  teammate_death: '팀원 사망',
}

const COBALT_OUTCOMES = ['승리', '패배']

export type RecordingStopped = 'before' | 'during' | null

/** 스팀 녹화가 오류로 멈춰 녹화가 없거나(before) 잘린(during) 게임에 붙이는 배지 문구. */
export function recordingStopLabel(stopped: RecordingStopped | undefined): string | null {
  if (stopped === 'before') return '스팀 녹화 오류로 녹화 없음'
  if (stopped === 'during') return '스팀 녹화 오류로 일부만 녹화'
  return null
}

export function gameHeadline(result: MatchResult | null, stopped?: RecordingStopped): string {
  if (!result && stopped === 'before') return '녹화 없음'

  if (result?.outcome && COBALT_OUTCOMES.includes(result.outcome)) return result.outcome
  if (!result) return '결과 미확인'
  if (result.placement == null) return '순위 미확인'
  return `#${result.placement}`
}

export function matchTypeLabel(result: MatchResult | null): string {
  if (result?.matchType === 'rank') return '랭크'
  if (result?.matchType === 'normal') return '일반'
  return ''
}

export function candidateTitle(c: Candidate): string {
  return c.user.title || c.title
}
