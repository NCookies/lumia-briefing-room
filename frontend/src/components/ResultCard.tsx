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
  games: { key: string; clipId: string; caption: string }[]
  index: number
  onIndexChange: (index: number) => void
  onClose: () => void
}

const NAV =
  'fixed top-1/2 z-[75] flex h-24 w-14 -translate-y-1/2 items-center justify-center rounded-xl bg-zinc-800/80 text-4xl text-zinc-100 hover:bg-zinc-600 disabled:cursor-default disabled:opacity-20 disabled:hover:bg-zinc-800/80'

export function ResultViewer({ games, index, onIndexChange, onClose }: ViewerProps) {
  const game = games[index]
  const hasPrev = index > 0
  const hasNext = index < games.length - 1

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowLeft' && hasPrev) onIndexChange(index - 1)
      if (e.key === 'ArrowRight' && hasNext) onIndexChange(index + 1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [index, hasPrev, hasNext, onIndexChange, onClose])

  return (
    <div className="fixed inset-0 z-[70] flex flex-col items-center justify-center gap-2 bg-black/90 p-2" onClick={onClose}>
      <button
        type="button"
        aria-label="이전 게임"
        className={`${NAV} left-2`}
        disabled={!hasPrev}
        onClick={(e) => {
          e.stopPropagation()
          onIndexChange(index - 1)
        }}
      >
        ‹
      </button>
      <button
        type="button"
        aria-label="다음 게임"
        className={`${NAV} right-2`}
        disabled={!hasNext}
        onClick={(e) => {
          e.stopPropagation()
          onIndexChange(index + 1)
        }}
      >
        ›
      </button>
      <div className="text-sm text-zinc-200" onClick={(e) => e.stopPropagation()}>
        {game.caption} · {index + 1}/{games.length}
      </div>
      <img
        src={resultImageUrl(game.clipId)}
        alt="결과표"
        className="max-h-[calc(100%-2rem)] max-w-full rounded"
        onClick={(e) => e.stopPropagation()}
      />
    </div>
  )
}
