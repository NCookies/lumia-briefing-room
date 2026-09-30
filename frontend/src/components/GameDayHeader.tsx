import { formatDayLabel } from '../gameDays'
import { formatBytes } from '../retention'

interface Props {
  day: string | null
  gameCount: number
  clipCount: number
  clipBytes: number
  bytesLabel?: string
  videoCount?: number
  collapsed?: boolean
  onToggle?: () => void
}

export function GameDayHeader({
  day,
  gameCount,
  clipCount,
  clipBytes,
  bytesLabel = '',
  videoCount,
  collapsed = false,
  onToggle,
}: Props) {
  const foldable = onToggle !== undefined
  return (
    <div
      className={`sticky top-0 z-10 -mx-4 flex items-baseline gap-3 border-b border-zinc-600 bg-zinc-900/95 px-4 py-2 backdrop-blur ${
        foldable ? 'cursor-pointer select-none hover:bg-zinc-800/95' : ''
      }`}
      {...(foldable
        ? {
            role: 'button',
            tabIndex: 0,
            'aria-expanded': !collapsed,
            onClick: onToggle,
            onKeyDown: (e: React.KeyboardEvent) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                onToggle()
              }
            },
          }
        : {})}
    >
      {foldable && (
        <span aria-hidden className="w-3 text-xs text-zinc-400">
          {collapsed ? '▶' : '▼'}
        </span>
      )}
      <h2 className="text-base font-semibold text-zinc-100">{formatDayLabel(day)}</h2>
      <span className="text-xs text-zinc-400">
        {videoCount !== undefined && `영상 ${videoCount}개 · `}게임 {gameCount}개 · 클립 {clipCount}개 · {bytesLabel}{formatBytes(clipBytes)}
      </span>
    </div>
  )
}
