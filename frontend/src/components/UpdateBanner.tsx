import { useState } from 'react'
import { installProgressText, isInstallBusy, releaseSummary } from '../update'
import { useUpdate } from '../updateContext'

export function UpdateBanner() {
  const { release, install, start, openNotes } = useUpdate()
  const [dismissedVersion, setDismissedVersion] = useState<string | null>(null)

  if (!release || dismissedVersion === release.version) return null
  const busy = isInstallBusy(install.state)
  const progress = installProgressText(install)

  return (
    <div
      className="flex flex-wrap items-center gap-3 border-b border-sky-800 bg-sky-950 px-4 py-2 text-sm text-sky-100"
      role="status"
    >
      <span>{releaseSummary(release)}이 나왔습니다.</span>
      <button
        type="button"
        className="rounded bg-sky-600 px-3 py-0.5 text-xs text-white hover:bg-sky-500 disabled:opacity-50"
        disabled={busy}
        onClick={start}
      >
        업데이트
      </button>
      <button type="button" className="text-xs text-sky-300 underline hover:text-sky-200" onClick={() => openNotes(release)}>
        변경 내용 보기
      </button>
      {progress && <span className={install.state === 'failed' ? 'text-rose-300' : 'text-sky-200'}>{progress}</span>}
      {!busy && (
        <button
          type="button"
          className="ml-auto text-xs text-sky-400 hover:text-sky-200"
          aria-label="닫기"
          title="이 버전 알림 닫기"
          onClick={() => setDismissedVersion(release.version)}
        >
          ✕
        </button>
      )}
    </div>
  )
}
