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

export const showUpdateBanner = (status: UpdateStatus): boolean => status.enabled && status.available !== null

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
