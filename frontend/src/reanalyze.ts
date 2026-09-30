export type ReanalyzeMode = 'full' | 'candidates'

export interface ReanalyzeStatus {
  state: 'idle' | 'running' | 'done' | 'error'
  message: string
  fraction: number
  mode: ReanalyzeMode | null
}

const KEEP = '보관한 클립·고정·직접 추가한 구간은 그대로 두고, 후보의 무시·이름·범위 수정은 초기화됩니다.'

export function reanalyzeConfirmMessage(mode: ReanalyzeMode): string {
  const newline = String.fromCharCode(10)
  if (mode === 'full') {
    return ['이 게임을 원본 스팀 녹화에서 다시 분석합니다.', `풀영상·교전 후보·결과표·초상화를 전부 새로 만듭니다. ${KEEP}`, '몇 분 걸릴 수 있습니다. 계속하시겠습니까?'].join(newline)
  }
  return [
    '원본 스팀 녹화가 이미 지워져 있어 저장한 풀영상에서 후보·결과표·초상화만 다시 찾습니다(풀영상은 그대로 둡니다).',
    KEEP,
    '몇 분 걸릴 수 있습니다. 계속하시겠습니까?',
  ].join(newline)
}

export function reanalyzeStatusText(status: ReanalyzeStatus): string | null {
  if (status.state === 'running') {
    const pct = Math.round(status.fraction * 100)
    return status.mode === 'full' ? `풀영상과 후보를 다시 만드는 중… ${pct}%` : `다시 분석하는 중… ${pct}%`
  }
  if (status.state === 'done') return status.mode === 'candidates' ? '후보를 다시 찾았습니다' : '풀영상과 후보를 다시 만들었습니다'
  if (status.state === 'error') return status.message || '다시 분석하지 못했습니다'
  return null
}
