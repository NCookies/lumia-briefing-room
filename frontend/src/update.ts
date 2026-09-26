export interface ReleaseInfo {
  version: string
  notes: string
  pageUrl: string
}

export type InstallState = 'idle' | 'downloading' | 'verifying' | 'launching' | 'launched' | 'failed'

export interface InstallStatus {
  state: InstallState
  downloaded: number
  total: number
  error: string
}

export interface UpdateStatus {
  enabled: boolean
  current: string
  lastChecked: number | null
  available: ReleaseInfo | null
  install: InstallStatus
}

export type CheckResult =
  | { state: 'available'; current: string; release: ReleaseInfo }
  | { state: 'latest'; current: string }
  | { state: 'error'; current: string; error: string }

export const showUpdateBanner = (status: UpdateStatus): boolean => status.available !== null

export const UPDATE_CHECKED_EVENT = 'lumia:update-checked'
export const UPDATE_STATUS_POLL_MS = 30000

export const isInstallBusy = (state: InstallState): boolean =>
  state === 'downloading' || state === 'verifying' || state === 'launching' || state === 'launched'

export const releaseSummary = (release: ReleaseInfo): string => `새 버전 v${release.version}`

export function installProgressText(install: InstallStatus): string {
  switch (install.state) {
    case 'downloading':
      return install.total > 0 ? `받는 중 ${Math.floor((install.downloaded / install.total) * 100)}%` : '받는 중…'
    case 'verifying':
      return 'SHA-256 확인 중…'
    case 'launching':
      return '설치기를 실행하는 중…'
    case 'launched':
      return '설치기를 실행했습니다. 앱이 곧 종료되고, 업데이트가 끝나면 다시 실행됩니다.'
    case 'failed':
      return install.error
    default:
      return ''
  }
}

export const RESTART_SLOW_AFTER_SEC = 30

export function restartProbe(o: { sawDown: boolean; reachable: boolean }): { sawDown: boolean; reload: boolean } {
  if (!o.reachable) return { sawDown: true, reload: false }
  return { sawDown: o.sawDown, reload: o.sawDown }
}

export function restartHint(elapsedSec: number): string {
  if (elapsedSec < RESTART_SLOW_AFTER_SEC) return ''
  return '보통 10~30초면 끝납니다. 이 화면이 그대로여도 업데이트는 이미 끝났을 수 있습니다. 작업 표시줄 오른쪽 ^ 안의 루미아 아이콘(트레이)을 누르거나, 시작 메뉴에서 "루미아 브리핑룸"을 실행하면 새 버전이 열립니다.'
}
