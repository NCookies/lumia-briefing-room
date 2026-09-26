import { createContext, useContext } from 'react'

export type AppMode = 'dev' | 'release'

export interface VideoFormats {
  supported: string[]
  verified: string[]
}

export interface AppInfo {
  version: string
  mode: AppMode
  videoFormats: VideoFormats
}

export const DEFAULT_APP_INFO: AppInfo = { version: '', mode: 'release', videoFormats: { supported: [], verified: [] } }

export function videoFormatHelpText(formats: VideoFormats): string {
  if (formats.supported.length === 0) return ''
  const lines = [`지원하는 영상 형식: ${formats.supported.join(' ')} (OBS 등 녹화 프로그램 영상)`]
  const unverified = formats.supported.filter((ext) => !formats.verified.includes(ext))
  lines.push(
    unverified.length === 0
      ? `확인된 형식: ${formats.verified.join(' ')}`
      : `확인된 형식: ${formats.verified.join(' ')} / 그 밖의 형식은 시도할 수 있지만 아직 확인되지 않았습니다.`,
  )
  return lines.join('\n')
}

export function showTuningUi(info: AppInfo): boolean {
  return info.mode === 'dev'
}

export function versionLabel(info: AppInfo): string {
  if (!info.version) return ''
  return info.mode === 'dev' ? `v${info.version} (dev)` : `v${info.version}`
}

export async function fetchAppInfo(): Promise<AppInfo> {
  const res = await fetch('/api/app-info')
  if (!res.ok) throw new Error(`앱 정보 불러오기에 실패했습니다 (${res.status})`)
  const body = await res.json()
  const formats = body.videoFormats ?? {}
  return {
    version: String(body.version ?? ''),
    mode: body.mode === 'dev' ? 'dev' : 'release',
    videoFormats: {
      supported: Array.isArray(formats.supported) ? formats.supported.map(String) : [],
      verified: Array.isArray(formats.verified) ? formats.verified.map(String) : [],
    },
  }
}

export const AppInfoContext = createContext<AppInfo>(DEFAULT_APP_INFO)

export const useAppInfo = (): AppInfo => useContext(AppInfoContext)

export const useTuningUi = (): boolean => showTuningUi(useAppInfo())
