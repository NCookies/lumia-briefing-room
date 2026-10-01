import { useEffect, useState } from 'react'
import { formatAgo } from '../grouping'
import { getWatchFailures, retryWatchFailure, type WatchFailure } from '../watchApi'

const POLL_MS = 5000

export function WatchFailureBanner() {
  const [failures, setFailures] = useState<WatchFailure[]>([])
  const [retrying, setRetrying] = useState<Set<string>>(new Set())

  useEffect(() => {
    let cancelled = false
    const poll = async () => {
      try {
        const next = await getWatchFailures()
        if (!cancelled) setFailures(next)
      } catch {
        // 서버가 잠깐 응답하지 못해도 화면은 그대로 둔다
      }
    }
    void poll()
    const timer = window.setInterval(poll, POLL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  if (failures.length === 0) return null

  const retry = (key: string) => {
    setRetrying((prev) => new Set(prev).add(key))
    retryWatchFailure(key)
      .catch(() => {})
      .finally(() => {
        setRetrying((prev) => {
          const next = new Set(prev)
          next.delete(key)
          return next
        })
      })
  }

  return (
    <div className="border-b border-rose-900/60 bg-rose-950/40" role="alert">
      {failures.map((f) => (
        <div key={f.key} className="flex flex-wrap items-center gap-3 px-4 py-2 text-sm text-rose-200">
          <span className="font-semibold text-rose-300">실시간 감시 중단됨</span>
          <span>{f.message}</span>
          <span className="text-xs text-rose-400/70">{formatAgo(f.occurredAt)}</span>
          <button
            type="button"
            className="ml-auto rounded-md bg-rose-600 px-3 py-0.5 text-xs text-white transition hover:bg-rose-500 disabled:opacity-50"
            disabled={retrying.has(f.key)}
            onClick={() => retry(f.key)}
          >
            {retrying.has(f.key) ? '다시 시도하는 중…' : '계속하기'}
          </button>
        </div>
      ))}
    </div>
  )
}
