import { useEffect, useState } from 'react'
import {
  describeProgress,
  describeResult,
  formatDuration,
  formatEstimate,
  isBackfillActive,
  progressPercent,
  type BackfillPreview,
  type BackfillStatus,
} from '../backfill'
import { cancelBackfill, getBackfillPreview, startBackfill } from '../backfillApi'
import { formatBytes } from '../retention'

interface Props {
  status: BackfillStatus
  onStatusChange: (status: BackfillStatus) => void
  onClose: () => void
}

export function BackfillDialog({ status, onStatusChange, onClose }: Props) {
  const [preview, setPreview] = useState<BackfillPreview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const active = isBackfillActive(status.state)
  const showPreview = !active && status.state !== 'done' && status.state !== 'cancelled'

  useEffect(() => {
    if (!showPreview) return
    getBackfillPreview()
      .then(setPreview)
      .catch((e: Error) => setError(e.message))
  }, [showPreview])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const start = async () => {
    setBusy(true)
    setError(null)
    try {
      await startBackfill()
      onStatusChange({ state: 'running', phase: 'scan', fraction: 0 })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const cancel = async () => {
    setBusy(true)
    try {
      onStatusChange(await cancelBackfill())
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const again = () => onStatusChange({ state: 'idle' })

  return (
    <div className="fixed inset-0 z-[85] flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className="flex w-full max-w-lg flex-col gap-4 rounded-lg border border-zinc-600 bg-zinc-800 p-5 text-zinc-100"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-medium">과거 녹화 전체 분석</h2>

        {showPreview && (
          <>
            <p className="text-sm leading-relaxed text-zinc-300">
              게임 로그에는 최근 두 번 실행한 분량만 남아 있어, 그 이전 게임은 자동으로 클립이 만들어지지 않습니다.
              스팀 녹화 영상을 직접 살펴보고 그런 게임을 찾아 클립으로 만듭니다.
            </p>
            {preview && preview.canStart && (
              <dl className="grid grid-cols-[6rem_1fr] gap-x-3 gap-y-1 rounded bg-zinc-900 p-3 text-sm">
                <dt className="text-zinc-500">대상</dt>
                <dd>
                  이터널 리턴 녹화 {preview.sessions}개 · {formatDuration(preview.videoSeconds ?? 0)} ·{' '}
                  {formatBytes(preview.sizeBytes ?? 0)}
                </dd>
                <dt className="text-zinc-500">예상 시간</dt>
                <dd className="font-medium text-sky-300">{formatEstimate(preview.estimatedSeconds ?? 0)}</dd>
              </dl>
            )}
            {preview && !preview.canStart && (
              <p className="rounded border border-amber-500/50 bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
                {preview.reason}
              </p>
            )}
            <ul className="list-disc space-y-1 pl-5 text-xs leading-relaxed text-zinc-400">
              <li>
                <b className="text-zinc-300">시간이 걸릴 수 있고 컴퓨터가 느려질 수 있습니다.</b> 예상 시간은 개발 PC에서 측정한 속도를 바탕으로 한
                추정값이라 사양에 따라 더 걸릴 수 있습니다. 게임을 종료한 뒤 실행하기를 권합니다.
              </li>
              <li>언제든 취소할 수 있습니다. 취소해도 이미 만든 클립은 그대로 남고, 다시 시작하면 이어서 합니다.</li>
              <li>
                스팀은 새 녹화가 쌓이면 오래된 녹화를 지웁니다. 앞부분이 이미 지워진 게임은 만들 수 없습니다.
              </li>
              <li>이미 클립이 있는 게임과 로그로 아는 게임은 건너뜁니다.</li>
            </ul>
          </>
        )}

        {active && (
          <div className="flex flex-col gap-2">
            <div className="flex items-baseline justify-between text-sm">
              <span>{describeProgress(status)}</span>
              <span className="tabular-nums text-zinc-400">{progressPercent(status)}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded bg-zinc-700">
              <div className="h-full bg-sky-500 transition-[width]" style={{ width: `${progressPercent(status)}%` }} />
            </div>
            <p className="text-xs text-zinc-500">
              이 창을 닫아도 분석은 계속됩니다. 헤더의 버튼에서 진행 상황을 볼 수 있습니다.
            </p>
          </div>
        )}

        {(status.state === 'done' || status.state === 'cancelled') && status.result && (
          <ul className="space-y-1 text-sm leading-relaxed text-zinc-200">
            {describeResult(status.result).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        )}

        {status.state === 'error' && (
          <p className="rounded border border-rose-500/50 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
            분석하지 못했습니다: {status.error}
          </p>
        )}
        {error && <p className="text-sm text-rose-300">{error}</p>}

        <div className="flex justify-end gap-2">
          {active ? (
            <button
              type="button"
              className="rounded border border-rose-500/60 px-4 py-1.5 text-sm text-rose-200 hover:bg-rose-500/10 disabled:opacity-40"
              disabled={busy}
              onClick={() => void cancel()}
            >
              분석 취소
            </button>
          ) : showPreview ? (
            <button
              type="button"
              className="rounded bg-sky-600 px-4 py-1.5 text-sm hover:bg-sky-500 disabled:opacity-40"
              disabled={busy || !preview?.canStart}
              onClick={() => void start()}
            >
              분석 시작
            </button>
          ) : (
            <button
              type="button"
              className={
                status.state === 'cancelled'
                  ? 'rounded bg-sky-600 px-4 py-1.5 text-sm hover:bg-sky-500 disabled:opacity-40'
                  : 'rounded border border-zinc-600 px-4 py-1.5 text-sm hover:bg-zinc-700'
              }
              disabled={busy}
              onClick={() => (status.state === 'cancelled' ? void start() : again())}
            >
              {status.state === 'cancelled' ? '이어서 하기' : '확인'}
            </button>
          )}
          <button type="button" className="rounded px-4 py-1.5 text-sm text-zinc-300 hover:bg-zinc-700" onClick={onClose}>
            닫기
          </button>
        </div>
      </div>
    </div>
  )
}
