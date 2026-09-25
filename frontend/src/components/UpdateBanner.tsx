import { useEffect, useState } from 'react'
import { installProgressText, isInstallBusy, releaseSummary, showUpdateBanner, type ReleaseInfo } from '../update'
import { getUpdateStatus } from '../updateApi'
import { useUpdateInstall } from '../useUpdateInstall'

export function UpdateBanner({ onOpenAbout }: { onOpenAbout: () => void }) {
  const [release, setRelease] = useState<ReleaseInfo | null>(null)
  const [dismissed, setDismissed] = useState(false)
  const { install, start } = useUpdateInstall()

  useEffect(() => {
    getUpdateStatus()
      .then((status) => setRelease(showUpdateBanner(status) ? status.available : null))
      .catch(() => {})
  }, [])

  if (!release || dismissed) return null
  const busy = isInstallBusy(install.state)
  const progress = installProgressText(install)

  return (
    <div className="flex items-center gap-3 border-b border-sky-800 bg-sky-950 px-4 py-2 text-sm text-sky-100" role="status">
      <span>{releaseSummary(release)} 이 나왔습니다.</span>
      <button
        type="button"
        className="rounded bg-sky-600 px-2 py-0.5 text-xs text-white hover:bg-sky-500 disabled:opacity-50"
        disabled={busy}
        onClick={start}
      >
        업데이트
      </button>
      <button type="button" className="text-xs text-sky-300 underline hover:text-sky-200" onClick={onOpenAbout}>
        패치노트·자세히
      </button>
      {progress && <span className={install.state === 'failed' ? 'text-rose-300' : 'text-sky-200'}>{progress}</span>}
      {!busy && (
        <button
          type="button"
          className="ml-auto text-xs text-sky-400 hover:text-sky-200"
          aria-label="닫기"
          onClick={() => setDismissed(true)}
        >
          ✕
        </button>
      )}
    </div>
  )
}
