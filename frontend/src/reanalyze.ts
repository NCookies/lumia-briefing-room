export type ReanalyzeMode = 'full' | 'candidates'

export interface ReanalyzeStatus {
  state: 'idle' | 'queued' | 'running' | 'done' | 'error'
  message: string
  fraction: number
  mode: ReanalyzeMode | null
  /** 대기 중일 때만: 1 = 다음 차례. */
  position?: number | null
}

export function reanalyzeConfirmMessage(): string {
  return ['이 게임을 다시 분석합니다.', '몇 분 정도 소요될 수 있습니다. 계속하시겠습니까?'].join(String.fromCharCode(10))
}

/** 대기 중 표시: "대기 중 (1번째)" = 지금 도는 작업 다음 차례. */
export function queueLabel(position: number | null | undefined): string {
  return position && position > 0 ? `대기 중 (${position}번째)` : '대기 중'
}

export function reanalyzeStatusText(status: ReanalyzeStatus): string | null {
  if (status.state === 'queued') return queueLabel(status.position)
  if (status.state === 'running') {
    const pct = Math.round(status.fraction * 100)
    return status.mode === 'full' ? `풀영상과 후보를 다시 만드는 중… ${pct}%` : `다시 분석하는 중… ${pct}%`
  }
  if (status.state === 'done') return status.mode === 'candidates' ? '후보를 다시 찾았습니다' : '풀영상과 후보를 다시 만들었습니다'
  if (status.state === 'error') return status.message || '다시 분석하지 못했습니다'
  return null
}
