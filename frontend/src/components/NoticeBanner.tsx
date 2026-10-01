import { useEffect, useState } from 'react'
import { dismissNotice, getNotices, type AppNotice } from '../noticeApi'

const POLL_MS = 10000

export function NoticeBanner() {
  const [notices, setNotices] = useState<AppNotice[]>([])

  useEffect(() => {
    let cancelled = false
    const poll = async () => {
      try {
        const next = await getNotices()
        if (!cancelled) setNotices(next)
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

  if (notices.length === 0) return null

  const close = (kind: string) => {
    setNotices((prev) => prev.filter((n) => n.kind !== kind))
    dismissNotice(kind).catch(() => {})
  }

  return (
    <div className="border-b border-amber-900/60 bg-amber-950/40" role="alert">
      {notices.map((n) => (
        <div key={n.kind} className="flex flex-wrap items-center gap-3 px-4 py-2 text-sm text-amber-200">
          <span className="font-semibold text-amber-300">{n.title}</span>
          <span>{n.message}</span>
          <button
            type="button"
            className="ml-auto rounded-md bg-amber-700 px-3 py-0.5 text-xs text-white transition hover:bg-amber-600"
            onClick={() => close(n.kind)}
          >
            닫기
          </button>
        </div>
      ))}
    </div>
  )
}
