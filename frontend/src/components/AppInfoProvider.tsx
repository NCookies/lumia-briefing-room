import { useEffect, useState, type ReactNode } from 'react'
import { AppInfoContext, DEFAULT_APP_INFO, fetchAppInfo, type AppInfo } from '../appInfo'

export function AppInfoProvider({ children }: { children: ReactNode }) {
  const [info, setInfo] = useState<AppInfo>(DEFAULT_APP_INFO)

  useEffect(() => {
    fetchAppInfo()
      .then(setInfo)
      .catch(() => {})
  }, [])

  return <AppInfoContext.Provider value={info}>{children}</AppInfoContext.Provider>
}
