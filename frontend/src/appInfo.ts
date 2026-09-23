import { createContext, useContext } from 'react'

export type AppMode = 'dev' | 'release'

export interface AppInfo {
  version: string
  mode: AppMode
}

export const DEFAULT_APP_INFO: AppInfo = { version: '', mode: 'release' }

export function showTuningUi(info: AppInfo): boolean {
  return info.mode === 'dev'
}

export async function fetchAppInfo(): Promise<AppInfo> {
  const res = await fetch('/api/app-info')
  if (!res.ok) throw new Error(`앱 정보 조회에 실패했습니다 (${res.status})`)
  const body = await res.json()
  return { version: String(body.version ?? ''), mode: body.mode === 'dev' ? 'dev' : 'release' }
}

export const AppInfoContext = createContext<AppInfo>(DEFAULT_APP_INFO)

export const useAppInfo = (): AppInfo => useContext(AppInfoContext)

export const useTuningUi = (): boolean => showTuningUi(useAppInfo())
