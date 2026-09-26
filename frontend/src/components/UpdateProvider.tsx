import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { useAppInfo } from '../appInfo'
import {
  UPDATE_CHECKED_EVENT,
  UPDATE_STATUS_POLL_MS,
  isInstallBusy,
  showUpdateBanner,
  type InstallStatus,
  type ReleaseInfo,
} from '../update'
import { IDLE_INSTALL, UpdateContext } from '../updateContext'
import { ackUpdate, getUpdateStatus, startUpdateInstall } from '../updateApi'
import { ReleaseNotesDialog } from './ReleaseNotesDialog'
import { UpdateOverlay } from './UpdateOverlay'
import { PatchNotesDialog } from './PatchNotesDialog'
import { UpdatedDialog } from './UpdatedDialog'

/** 새 버전과 설치 진행 상태를 화면 전체가 함께 쓴다. 창을 닫았다 열어도 진행도가 이어져 보이도록 서버의 상태를 읽어 온다. */
export function UpdateProvider({ children }: { children: ReactNode }) {
  const info = useAppInfo()
  const [release, setRelease] = useState<ReleaseInfo | null>(null)
  const [install, setInstall] = useState<InstallStatus>(IDLE_INSTALL)
  const [notes, setNotes] = useState<ReleaseInfo | null>(null)
  const [justUpdated, setJustUpdated] = useState<{ from: string; to: string } | null>(null)
  const [patchNotes, setPatchNotes] = useState(false)

  const refresh = useCallback(() => {
    getUpdateStatus()
      .then((status) => {
        setRelease(showUpdateBanner(status) ? status.available : null)
        setInstall(status.install)
        setJustUpdated(status.justUpdated ?? null)
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    refresh()
    const timer = window.setInterval(refresh, UPDATE_STATUS_POLL_MS)
    window.addEventListener(UPDATE_CHECKED_EVENT, refresh)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener(UPDATE_CHECKED_EVENT, refresh)
    }
  }, [refresh])

  const inProgress = isInstallBusy(install.state) && install.state !== 'launched'
  useEffect(() => {
    if (!inProgress) return
    const timer = window.setInterval(refresh, 1000)
    return () => window.clearInterval(timer)
  }, [inProgress, refresh])

  const start = useCallback(() => {
    setInstall({ ...IDLE_INSTALL, state: 'downloading' })
    startUpdateInstall()
      .then((status) => setInstall(status.install))
      .catch((e: Error) => setInstall({ ...IDLE_INSTALL, state: 'failed', error: e.message }))
  }, [])

  return (
    <UpdateContext.Provider value={{ release, install, start, refresh, openNotes: setNotes }}>
      {children}
      {notes && (
        <ReleaseNotesDialog
          release={notes}
          currentVersion={info.version}
          busy={isInstallBusy(install.state)}
          onUpdate={start}
          onClose={() => setNotes(null)}
        />
      )}
      {justUpdated && install.state !== 'launched' && (
        <UpdatedDialog
          from={justUpdated.from}
          to={justUpdated.to}
          onClose={() => {
            setJustUpdated(null)
            ackUpdate().catch(() => {})
          }}
          onShowNotes={() => {
            setJustUpdated(null)
            ackUpdate().catch(() => {})
            setPatchNotes(true)
          }}
        />
      )}
      {patchNotes && <PatchNotesDialog onClose={() => setPatchNotes(false)} />}
      {install.state === 'launched' && <UpdateOverlay version={release?.version ?? ''} />}
    </UpdateContext.Provider>
  )
}
