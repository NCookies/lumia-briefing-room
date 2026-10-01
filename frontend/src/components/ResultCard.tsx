import { useEffect } from 'react'
import { formatMatchResult } from '../grouping'
import type { MatchResult } from '../types'

interface CardProps {
  imageUrl: string
  result: MatchResult
  onOpen: () => void
}

export function ResultCard({ imageUrl, result, onOpen }: CardProps) {
  return (
    <button
      type="button"
      className="group relative aspect-video w-full overflow-hidden rounded-lg border border-zinc-600/70 bg-zinc-900"
      onClick={onOpen}
      title="결과표 크게 보기"
    >
      <img
        src={imageUrl}
        alt="결과표"
        className="h-full w-full object-cover transition-transform group-hover:scale-105"
      />
      <span className="absolute left-1 top-1 rounded-md bg-black/70 px-1.5 py-0.5 text-xs text-zinc-100">결과표</span>
      <span
        className={`absolute bottom-1 left-1 right-1 truncate rounded-md px-1.5 py-0.5 text-sm font-medium ${
          result.placement === 1 ? 'bg-amber-400/90 text-zinc-900' : 'bg-black/70 text-zinc-100'
        }`}
      >
        {formatMatchResult(result)}
      </span>
    </button>
  )
}

interface ViewerProps {
  games: { key: string; imageUrl: string; caption: string }[]
  index: number
  onIndexChange: (index: number) => void
  onClose: () => void
}

const NAV =
  'fixed top-1/2 z-[75] flex h-24 w-14 -translate-y-1/2 items-center justify-center rounded-xl bg-zinc-800/80 text-4xl text-zinc-100 transition hover:bg-zinc-600 disabled:cursor-default disabled:opacity-20 disabled:hover:bg-zinc-800/80'

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
    <div className="fixed inset-0 z-[70] flex flex-col items-center justify-center gap-2 bg-black/90 p-2">
      <button
        type="button"
        aria-label="닫기"
        className="fixed right-2 top-2 z-[75] rounded-md px-2 py-1 text-2xl text-zinc-300 transition hover:bg-zinc-700 hover:text-zinc-100"
        onClick={onClose}
      >
        ✕
      </button>
      <button
        type="button"
        aria-label="이전 게임"
        className={`${NAV} left-2`}
        disabled={!hasPrev}
        onClick={() => onIndexChange(index - 1)}
      >
        ‹
      </button>
      <button
        type="button"
        aria-label="다음 게임"
        className={`${NAV} right-2`}
        disabled={!hasNext}
        onClick={() => onIndexChange(index + 1)}
      >
        ›
      </button>
      <div className="text-sm text-zinc-200">
        {game.caption} · {index + 1}/{games.length}
      </div>
      <img src={game.imageUrl} alt="결과표" className="max-h-[calc(100%-2rem)] max-w-full rounded-md" />
    </div>
  )
}
