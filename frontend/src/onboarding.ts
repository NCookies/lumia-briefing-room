export type ResolutionKind = 'measured' | 'scaled' | 'unsupported_ratio'

export interface RecordingReport {
  root: string | null
  source: 'config' | 'auto' | null
  exists: boolean
  session: { name: string; width: number; height: number; codec: string | null } | null
  resolution: { kind: ResolutionKind; message: string; width: number; height: number } | null
}

export interface FirstRunInfo {
  needed: boolean
  pendingItems: string[]
  answeredVersion: number
  currentVersion: number
  recording: RecordingReport
  clipsDir: string
  ffmpegFound: boolean
}

export type RecordingState = 'ok' | 'no-root' | 'missing-folder' | 'no-session'

export function recordingState(report: RecordingReport): RecordingState {
  if (!report.root) return 'no-root'
  if (!report.exists) return 'missing-folder'
  if (!report.session) return 'no-session'
  return 'ok'
}

export const RECORDING_STATE_TEXT: Record<RecordingState, string> = {
  ok: '녹화 폴더를 찾았습니다.',
  'no-root': '스팀 녹화 폴더를 자동으로 찾지 못했습니다. 아래에서 직접 골라 주세요.',
  'missing-folder': '설정된 녹화 폴더가 없습니다. 아래에서 다시 골라 주세요.',
  'no-session':
    '폴더는 있지만 아직 녹화 기록이 없습니다. 스팀의 배경 녹화를 켜고 게임을 한 판 한 뒤 다시 확인하세요.',
}

export const RESOLUTION_TONE: Record<ResolutionKind, 'ok' | 'info' | 'warn'> = {
  measured: 'ok',
  scaled: 'info',
  unsupported_ratio: 'warn',
}

export const SOURCE_TEXT: Record<'config' | 'auto', string> = {
  config: '설정에서 지정한 폴더',
  auto: '스팀 설정에서 자동으로 찾은 폴더',
}
