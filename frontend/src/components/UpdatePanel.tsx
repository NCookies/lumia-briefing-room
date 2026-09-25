import { useState } from 'react'
import { installProgressText, isInstallBusy, releaseSummary, type CheckResult } from '../update'
import { checkForUpdate } from '../updateApi'
import { useUpdateInstall } from '../useUpdateInstall'

export function UpdatePanel() {
  const [checking, setChecking] = useState(false)
  const [result, setResult] = useState<CheckResult | null>(null)
  const { install, start } = useUpdateInstall()
  const busy = isInstallBusy(install.state)

  const check = () => {
    setChecking(true)
    checkForUpdate()
      .then(setResult)
      .catch((e: Error) => setResult({ state: 'error', current: '', error: e.message }))
      .finally(() => setChecking(false))
  }

  const progress = installProgressText(install)

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="w-fit rounded border border-zinc-600 px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
          disabled={checking || busy}
          onClick={check}
        >
          {checking ? '확인 중…' : '지금 확인'}
        </button>
        {result?.state === 'latest' && <span className="text-xs text-emerald-300">최신 버전입니다.</span>}
        {result?.state === 'error' && <span className="text-xs text-rose-300">{result.error}</span>}
      </div>
      {result?.state === 'available' && (
        <div className="flex flex-col gap-1 rounded border border-sky-700 bg-sky-950/40 p-2">
          <p className="text-sm text-sky-200">{releaseSummary(result.release)} 이 있습니다.</p>
          {result.release.notes && (
            <pre className="max-h-32 overflow-auto whitespace-pre-wrap text-xs text-zinc-400">{result.release.notes}</pre>
          )}
          <button
            type="button"
            className="w-fit rounded bg-sky-600 px-2 py-1 text-xs text-white hover:bg-sky-500 disabled:opacity-50"
            disabled={busy}
            onClick={start}
          >
            업데이트
          </button>
          {progress && (
            <p className={`text-xs ${install.state === 'failed' ? 'text-rose-300' : 'text-zinc-300'}`}>{progress}</p>
          )}
        </div>
      )}
      <p className="text-xs text-zinc-500">누를 때만 인터넷을 씁니다. 자동 확인 설정과는 별개로 동작합니다.</p>
    </div>
  )
}
