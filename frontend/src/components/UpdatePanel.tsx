import { useState } from 'react'
import { useAppInfo } from '../appInfo'
import { UPDATE_CHECKED_EVENT, installProgressText, isInstallBusy, releaseSummary, type CheckResult } from '../update'
import { checkForUpdate } from '../updateApi'
import { useUpdate } from '../updateContext'

export function UpdatePanel() {
  const info = useAppInfo()
  const { release: knownRelease, install, start, openNotes } = useUpdate()
  const [checking, setChecking] = useState(false)
  const [result, setResult] = useState<CheckResult | null>(null)
  const busy = isInstallBusy(install.state)

  const check = () => {
    setChecking(true)
    checkForUpdate()
      .then((next) => {
        setResult(next)
        window.dispatchEvent(new Event(UPDATE_CHECKED_EVENT))
      })
      .catch((e: Error) => setResult({ state: 'error', current: '', error: e.message }))
      .finally(() => setChecking(false))
  }

  const release = result?.state === 'available' ? result.release : result === null || result.state === 'error' ? knownRelease : null
  const progress = installProgressText(install)

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="w-fit rounded border border-zinc-600 px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
          disabled={checking || busy}
          title={busy ? '업데이트를 진행하는 중입니다' : undefined}
          onClick={check}
        >
          {checking ? '확인 중…' : '업데이트 확인'}
        </button>
        {result?.state === 'latest' && <span className="text-xs text-emerald-300">최신 버전입니다.</span>}
        {result?.state === 'error' && <span className="text-xs text-rose-300">{result.error}</span>}
      </div>

      {release && (
        <div className="flex flex-col gap-2 rounded-lg border border-sky-700 bg-sky-950/40 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-sm font-medium text-sky-100">{releaseSummary(release)}이 나왔습니다</p>
              <p className="text-xs text-sky-300/70">
                {info.version ? `현재 v${info.version} → v${release.version}` : `v${release.version}`}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="rounded border border-sky-600/60 px-3 py-1 text-xs text-sky-200 hover:bg-sky-500/20"
                onClick={() => openNotes(release)}
              >
                변경 내용 보기
              </button>
              <button
                type="button"
                className="rounded bg-sky-600 px-3 py-1 text-xs text-white hover:bg-sky-500 disabled:opacity-50"
                disabled={busy}
                onClick={start}
              >
                업데이트
              </button>
            </div>
          </div>
          {busy && install.state === 'downloading' && install.total > 0 && (
            <div className="h-1.5 overflow-hidden rounded bg-sky-900/60">
              <div
                className="h-full rounded bg-sky-400 transition-[width]"
                style={{ width: `${Math.min(100, Math.floor((install.downloaded / install.total) * 100))}%` }}
              />
            </div>
          )}
          {busy && install.state === 'downloading' && install.total === 0 && (
            <div className="h-1.5 overflow-hidden rounded bg-sky-900/60">
              <div className="indeterminate-bar h-full rounded bg-sky-400" />
            </div>
          )}
          {progress && (
            <p className={`text-xs ${install.state === 'failed' ? 'text-rose-300' : 'text-zinc-300'}`}>{progress}</p>
          )}
        </div>
      )}

      <p className="text-xs text-zinc-500">
        업데이트를 확인할 때만 인터넷을 사용합니다. &quot;업데이트 알림&quot; 설정과는 별개로 동작합니다.
      </p>
    </div>
  )
}
