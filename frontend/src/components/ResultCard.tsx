import { useEffect } from 'react'
import { resultImageUrl } from '../api'
import { formatMatchResult } from '../grouping'
import type { MatchResult } from '../types'

interface CardProps {
  clipId: string
  result: MatchResult
  onOpen: () => void
}

export function ResultCard({ clipId, result, onOpen }: CardProps) {
  return (
    <button
      type="button"
      className="group relative aspect-video w-full overflow-hidden rounded-lg border border-zinc-600 bg-zinc-900"
      onClick={onOpen}
      title="결과표 크게 보기"
    >
      <img
        src={resultImageUrl(clipId)}
        alt="결과표"
        className="h-full w-full object-cover transition-transform group-hover:scale-105"
      />
      <span className="absolute left-1 top-1 rounded bg-black/70 px-1.5 py-0.5 text-xs text-zinc-100">결과표</span>
      <span
        className={`absolute bottom-1 left-1 right-1 truncate rounded px-1.5 py-0.5 text-sm font-medium ${
          result.placement === 1 ? 'bg-amber-400/90 text-zinc-900' : 'bg-black/70 text-zinc-100'
        }`}
      >
        {formatMatchResult(result)}
      </span>
    </button>
  )
}

interface ViewerProps {
  clipId: string
  onClose: () => void
}

export function ResultViewer({ clipId, onClose }: ViewerProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/90 p-2" onClick={onClose}>
      <img
        src={resultImageUrl(clipId)}
        alt="결과표"
        className="max-h-full max-w-full rounded"
        onClick={(e) => e.stopPropagation()}
      />
    </div>
  )
}
