import { formatDayLabel } from '../gameDays'
import { formatBytes } from '../retention'

interface Props {
  day: string | null
  gameCount: number
  clipCount: number
  clipBytes: number
  bytesLabel?: string
}

export function GameDayHeader({ day, gameCount, clipCount, clipBytes, bytesLabel = '' }: Props) {
  return (
    <div className="sticky top-0 z-10 -mx-4 flex items-baseline gap-3 border-b border-zinc-600 bg-zinc-900/95 px-4 py-2 backdrop-blur">
      <h2 className="text-base font-semibold text-zinc-100">{formatDayLabel(day)}</h2>
      <span className="text-xs text-zinc-400">
        게임 {gameCount}개 · 클립 {clipCount}개 · {bytesLabel}{formatBytes(clipBytes)}
      </span>
    </div>
  )
}
