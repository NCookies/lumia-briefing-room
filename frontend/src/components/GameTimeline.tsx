import type { ReactNode } from 'react'
import { buildCobaltPhaseColumns, buildPhaseColumns } from '../timeline'
import type { Clip } from '../types'

interface Props {
  clips: Clip[]
  lead?: ReactNode
  renderClip: (clip: Clip) => ReactNode
  gameMode?: string | null
}

export function GameTimeline({ clips, lead, renderClip, gameMode }: Props) {
  const columns = gameMode === 'cobalt' ? buildCobaltPhaseColumns(clips) : buildPhaseColumns(clips)
  const firstCredit = columns.findIndex((c) => c.zone === 'credit')

  return (
    <div className="flex gap-3 overflow-x-auto pb-2">
      {lead && <div className="w-60 shrink-0">{lead}</div>}
      {columns.map((col, i) => (
        <div
          key={col.phaseIndex ?? 'unknown'}
          className={`flex w-60 shrink-0 flex-col gap-3 ${i === firstCredit ? 'border-l-2 border-amber-500/60 pl-3' : ''}`}
        >
          <div className="flex items-baseline justify-between border-b border-zinc-700 pb-1 text-sm">
            <span className="font-semibold text-zinc-200">{col.label}</span>
            <span className="text-xs text-zinc-500">
              {col.zone === 'credit' && i === firstCredit ? '크레딧 부활 구간 · ' : ''}
              {col.clips.length > 0 ? `${col.clips.length}개` : '교전 없음'}
            </span>
          </div>
          {col.clips.map((clip) => renderClip(clip))}
        </div>
      ))}
    </div>
  )
}
