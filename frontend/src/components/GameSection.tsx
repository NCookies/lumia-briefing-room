import type { ReactNode } from 'react'
import { formatAgo, formatKda, formatTeammates, totalSize, type GameGroup } from '../grouping'
import { formatBytes } from '../retention'
import type { Clip } from '../types'

interface Props {
  group: GameGroup<Clip>
  expanded: boolean
  trashed: boolean
  onToggle: () => void
  onTrashGame: () => void
  onRestoreGame: () => void
  onDeleteGameForever: () => void
  onReprocess: () => void
  reprocessing: boolean
  reprocessBusy: boolean
  timeLabel?: { main: string; sub?: string }
  hideReprocess?: boolean
  onDeleteRecord?: () => void
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

export function GameSection({
  group,
  expanded,
  trashed,
  onToggle,
  onTrashGame,
  onRestoreGame,
  onDeleteGameForever,
  onReprocess,
  reprocessing,
  reprocessBusy,
  timeLabel,
  hideReprocess,
  onDeleteRecord,
  children,
}: Props) {
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

          <div className={timeLabel ? 'w-44 text-sm' : 'w-28 text-sm'}>
            <div className="text-zinc-200">{timeLabel ? timeLabel.main : formatStart(group.matchStartUtc)}</div>
            <div className="text-xs text-zinc-500">{timeLabel ? timeLabel.sub : formatAgo(group.matchStartUtc)}</div>
          </div>

          <div className="w-40 text-sm text-zinc-200">
            <div>{result?.character ?? ''}</div>
            {formatTeammates(result) && <div className="truncate text-xs text-zinc-400">{formatTeammates(result)}</div>}
          </div>

          <div className="w-28">
            {kda && (
              <>
                <div className="text-base font-bold text-zinc-100">{kda}</div>
                <div className="text-xs text-zinc-500">TK / K / A</div>
              </>
            )}
          </div>

          <div className="ml-auto text-right text-sm text-zinc-400">
            {group.recordId ? (
              <div className="text-zinc-500">클립 삭제됨</div>
            ) : (
              <>
                <div>클립 {group.clips.length}개</div>
                <div className="text-xs text-zinc-500">{formatBytes(totalSize(group.clips))}</div>
              </>
            )}
          </div>
        </button>
        <div className="flex shrink-0 items-center gap-3 px-3 text-xs">
          {group.recordId ? (
            <button type="button" className="text-zinc-400 hover:text-rose-400" onClick={onDeleteRecord}>
              기록 삭제
            </button>
          ) : trashed ? (
            <>
              <button type="button" className="text-sky-400 hover:underline" onClick={onRestoreGame}>
                게임 복구
              </button>
              <button type="button" className="text-rose-400 hover:underline" onClick={onDeleteGameForever}>
                게임 완전 삭제
              </button>
            </>
          ) : (
            <>
              {!hideReprocess && (
                <button
                  type="button"
                  className="text-zinc-400 hover:text-sky-300 disabled:opacity-50 disabled:hover:text-zinc-400"
                  disabled={reprocessBusy}
                  title="원본 녹화에서 이 게임을 처음부터 다시 분석합니다"
                  onClick={onReprocess}
                >
                  {reprocessing ? '분석 중...' : '다시 분석'}
                </button>
              )}
              <button type="button" className="text-zinc-400 hover:text-rose-400" onClick={onTrashGame}>
                게임 삭제
              </button>
            </>
          )}
        </div>
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
