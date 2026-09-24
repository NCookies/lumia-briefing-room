export type BackfillState = 'idle' | 'running' | 'done' | 'cancelled' | 'error'

export interface BackfillSkipped {
  known: number
  cutAtStart: number
  stillRunning: number
  alreadyDone: number
  gaveUp: number
}

export interface BackfillResult {
  sessionsScanned: number
  gamesFound: number
  gamesProcessed: number
  gamesFailed: number
  clipsCreated: number
  cancelled: boolean
  skipped: BackfillSkipped
}

export interface BackfillStatus {
  state: BackfillState
  phase?: 'scan' | 'process' | 'done'
  fraction?: number
  message?: string
  sessionIndex?: number
  sessionTotal?: number
  gamesDone?: number
  gamesTotal?: number
  clips?: number
  error?: string | null
  result?: BackfillResult | null
}

export interface BackfillPreview {
  recordingRoot: string | null
  canStart: boolean
  reason: string | null
  sessions?: number
  segments?: number
  videoSeconds?: number
  sizeBytes?: number
  unscannedSeconds?: number
  estimatedSeconds?: number
}

export function isBackfillActive(state: BackfillState): boolean {
  return state === 'running'
}

export function progressPercent(status: BackfillStatus): number {
  return Math.round(Math.max(0, Math.min(1, status.fraction ?? 0)) * 100)
}

export function formatDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60)
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  if (h === 0) return `${m}분`
  return m === 0 ? `${h}시간` : `${h}시간 ${m}분`
}

export function formatEstimate(seconds: number): string {
  if (seconds < 60) return '1분 미만'
  return `약 ${formatDuration(Math.ceil(seconds / 60) * 60)}`
}

export function describeProgress(status: BackfillStatus): string {
  const extra = status.message ? [status.message] : []
  if (status.phase === 'process') {
    return [
      '게임 분석 중',
      `${(status.gamesDone ?? 0) + 1}/${status.gamesTotal ?? 0}`,
      `클립 ${status.clips ?? 0}개`,
      ...extra,
    ].join(' · ')
  }
  const session = status.sessionTotal ? [`세션 ${status.sessionIndex}/${status.sessionTotal}`] : []
  return ['녹화를 살펴보는 중', ...session, ...extra].join(' · ')
}

export function describeResult(result: BackfillResult): string[] {
  const lines: string[] = []
  if (result.cancelled) {
    lines.push(
      `취소했습니다. 그때까지 끝낸 게임 ${result.gamesProcessed}개(클립 ${result.clipsCreated}개)는 그대로 남아 있습니다.`,
    )
    lines.push('다시 시작하면 이어서 진행합니다. 이미 살펴본 녹화는 다시 확인하지 않습니다.')
  } else if (result.gamesProcessed === 0) {
    lines.push('새로 만들 게임이 없습니다.')
  } else {
    lines.push(`게임 ${result.gamesProcessed}개에서 클립 ${result.clipsCreated}개를 만들었습니다.`)
  }
  const skipped = result.skipped
  if (skipped.known > 0) lines.push(`이미 클립이 있는 게임 ${skipped.known}개는 건너뛰었습니다.`)
  if (skipped.cutAtStart > 0) {
    lines.push(`앞부분이 이미 지워진 게임 ${skipped.cutAtStart}개는 건너뛰었습니다(스팀이 오래된 녹화를 지웁니다).`)
  }
  if (skipped.stillRunning > 0) lines.push(`아직 진행 중인 게임 ${skipped.stillRunning}개는 끝난 뒤 자동으로 만들어집니다.`)
  if (result.gamesFailed > 0) lines.push(`실패한 게임 ${result.gamesFailed}개는 다시 시작하면 한 번 더 시도합니다.`)
  if (skipped.gaveUp > 0) lines.push(`여러 번 실패해 건너뛴 게임 ${skipped.gaveUp}개가 있습니다. 진단 정보를 보내 주세요.`)
  return lines
}
