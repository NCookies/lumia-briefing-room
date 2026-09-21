import type { ReactNode } from 'react'
import { formatAgo, formatKda, type GameGroup } from '../grouping'
import type { Clip } from '../types'

interface Props {
  group: GameGroup<Clip>
  expanded: boolean
  onToggle: () => void
  children: ReactNode
}

function formatStart(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function barColor(placement: number | undefined): string {
  if (placement === 1) return 'bg-emerald-500'
  if (placement !== undefined && placement <= 3) return 'bg-sky-500'
  return 'bg-zinc-500'
}

export function GameSection({ group, expanded, onToggle, children }: Props) {
  const result = group.result
  const kda = formatKda(result)

  return (
    <section className="overflow-hidden rounded-lg border border-zinc-700 bg-zinc-800/60">
      <div className="flex items-stretch">
        <div className={`w-1.5 shrink-0 ${barColor(result?.placement)}`} />
        <button
          type="button"
          className="flex flex-1 flex-wrap items-center gap-x-8 gap-y-2 px-4 py-3 text-left hover:bg-zinc-700/30"
          onClick={onToggle}
          aria-expanded={expanded}
        >
          <div className="w-24">
            {result ? (
              <>
                <div className={`text-xl font-bold ${result.placement === 1 ? 'text-emerald-400' : 'text-zinc-200'}`}>
                  #{result.placement}
                </div>
                <div className="text-sm font-semibold text-zinc-300">
                  {result.matchType === 'rank' ? '랭크' : result.matchType === 'normal' ? '일반' : ''}
                  {result.outcome?.includes('탈출') && <span className="ml-1 text-amber-300">탈출</span>}
                </div>
              </>
            ) : (
              <>
                <div className="text-base font-semibold text-zinc-400">게임 {group.number}</div>
                <div className="text-xs text-zinc-500">결과 미확인</div>
              </>
            )}
          </div>

          <div className="w-28 text-sm">
            <div className="text-zinc-200">{formatStart(group.matchStartUtc)}</div>
            <div className="text-xs text-zinc-500">{formatAgo(group.matchStartUtc)}</div>
          </div>

          <div className="w-28 text-sm text-zinc-200">{result?.character ?? ''}</div>

          <div className="w-28">
            {kda && (
              <>
                <div className="text-base font-bold text-zinc-100">{kda}</div>
                <div className="text-xs text-zinc-500">TK / K / A</div>
              </>
            )}
          </div>

          <div className="ml-auto text-sm text-zinc-400">클립 {group.clips.length}개</div>
        </button>
        <button
          type="button"
          className="w-14 shrink-0 border-l border-zinc-700 text-lg text-zinc-400 hover:bg-zinc-700/40 hover:text-zinc-100"
          onClick={onToggle}
          aria-label={expanded ? '접기' : '펼치기'}
        >
          {expanded ? '▴' : '▾'}
        </button>
      </div>

      {expanded && (
        <div className="grid grid-cols-1 gap-4 border-t border-zinc-700 p-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {children}
        </div>
      )}
    </section>
  )
}
