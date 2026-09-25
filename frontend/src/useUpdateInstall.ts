import { useCallback, useEffect, useRef, useState } from 'react'
import { isInstallBusy, type InstallStatus } from './update'
import { getUpdateStatus, startUpdateInstall } from './updateApi'

const IDLE: InstallStatus = { state: 'idle', downloaded: 0, total: 0, error: '' }

export function useUpdateInstall() {
  const [install, setInstall] = useState<InstallStatus>(IDLE)
  const timer = useRef<number | null>(null)

  const stopPolling = useCallback(() => {
    if (timer.current !== null) window.clearInterval(timer.current)
    timer.current = null
  }, [])

  useEffect(() => stopPolling, [stopPolling])

  const poll = useCallback(() => {
    stopPolling()
    timer.current = window.setInterval(() => {
      getUpdateStatus()
        .then((status) => {
          setInstall(status.install)
          if (!isInstallBusy(status.install.state)) stopPolling()
        })
        .catch(() => {
          // 설치기가 뜨면 앱이 곧 종료돼 응답이 끊긴다 — 마지막 상태를 그대로 둔다
          stopPolling()
        })
    }, 1000)
  }, [stopPolling])

  const start = useCallback(() => {
    setInstall({ ...IDLE, state: 'downloading' })
    startUpdateInstall()
      .then((status) => {
        setInstall(status.install)
        if (isInstallBusy(status.install.state)) poll()
      })
      .catch((e: Error) => setInstall({ ...IDLE, state: 'failed', error: e.message }))
  }, [poll])

  return { install, start }
}
