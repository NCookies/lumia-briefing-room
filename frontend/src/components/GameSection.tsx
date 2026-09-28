import { useState, type ReactNode } from 'react'
import { formatAgo, formatKda, totalSize, type GameGroup } from '../grouping'
import { formatBytes } from '../retention'
import type { Clip } from '../types'
import { PortraitRow } from './PortraitRow'

interface Props {
  group: GameGroup<Clip>
  expanded: boolean
  onToggle: () => void
  onDeleteGame: () => void
  onReprocess: () => void
  reprocessing: boolean
  reprocessBusy: boolean
  timeLabel?: { main: string; sub?: string }
  hideReprocess?: boolean
  onDeleteRecord?: () => void
  bare?: boolean
  matchResultLocked?: boolean
  onCorrectMatchResult?: (values: { placement: number; outcome: string }) => void
  onUnlockMatchResult?: () => void
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

interface MatchResultFormProps {
  placement: number | undefined
  outcome: string | null | undefined
  locked?: boolean
  onSave: (values: { placement: number; outcome: string }) => void
  onUnlock?: () => void
  onCancel: () => void
}

function MatchResultForm({ placement, outcome, locked, onSave, onUnlock, onCancel }: MatchResultFormProps) {
  const [p, setP] = useState(String(placement ?? ''))
  const [o, setO] = useState(outcome ?? '')

  return (
    <div
      className="flex flex-col gap-1 rounded border border-zinc-600 bg-zinc-900 p-2 text-xs"
      onClick={(e) => e.stopPropagation()}
    >
      <label className="flex items-center gap-1">
        순위
        <input
          type="number"
          min={1}
          className="w-14 rounded border border-zinc-600 bg-zinc-800 px-1 py-0.5 text-zinc-100"
          value={p}
          onChange={(e) => setP(e.target.value)}
        />
      </label>
      <label className="flex items-center gap-1">
        결과 문구
        <input
          type="text"
          className="w-32 rounded border border-zinc-600 bg-zinc-800 px-1 py-0.5 text-zinc-100"
          value={o}
          onChange={(e) => setO(e.target.value)}
        />
      </label>
      <div className="flex gap-2">
        <button
          type="button"
          className="text-sky-400 hover:underline disabled:opacity-40"
          disabled={!p || Number(p) < 1}
          onClick={() => onSave({ placement: Number(p), outcome: o })}
        >
          저장(잠금)
        </button>
        {locked && onUnlock && (
          <button type="button" className="text-amber-400 hover:underline" onClick={onUnlock}>
            잠금 해제
          </button>
        )}
        <button type="button" className="text-zinc-400 hover:underline" onClick={onCancel}>
          취소
        </button>
      </div>
    </div>
  )
}

export function GameSection({
  group,
  expanded,
  onToggle,
  onDeleteGame,
  onReprocess,
  reprocessing,
  reprocessBusy,
  timeLabel,
  hideReprocess,
  onDeleteRecord,
  bare,
  matchResultLocked,
  onCorrectMatchResult,
  onUnlockMatchResult,
  children,
}: Props) {
  const result = group.result
  const kda = formatKda(result)
  const [editing, setEditing] = useState(false)
  const canCorrect = Boolean(onCorrectMatchResult) && !group.recordId

  return (
    <section
      className={`overflow-hidden rounded-lg border bg-zinc-800/60 ${reprocessing ? 'border-sky-500/60' : 'border-zinc-700'}`}
    >
      <div className="flex items-stretch">
        <div className={`w-1.5 shrink-0 ${barColor(result?.placement)}`} />
        <div
          role="button"
          tabIndex={0}
          className="flex flex-1 flex-wrap items-center gap-x-8 gap-y-2 px-4 py-3 text-left hover:bg-zinc-700/30"
          onClick={onToggle}
          onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onToggle()}
          aria-expanded={expanded}
        >
          <div className="w-24">
            {editing ? (
              <MatchResultForm
                placement={result?.placement}
                outcome={result?.outcome}
                locked={matchResultLocked}
                onSave={(values) => {
                  onCorrectMatchResult?.(values)
                  setEditing(false)
                }}
                onUnlock={
                  onUnlockMatchResult
                    ? () => {
                        onUnlockMatchResult()
                        setEditing(false)
                      }
                    : undefined
                }
                onCancel={() => setEditing(false)}
              />
            ) : result ? (
              <div className="group/result flex items-start gap-1">
                <div>
                  <div className={`text-xl font-bold ${result.placement === 1 ? 'text-emerald-400' : 'text-zinc-200'}`}>
                    #{result.placement}
                    {matchResultLocked && (
                      <span className="ml-1 align-middle text-xs text-amber-400" title="수동으로 고정한 값입니다">
                        🔒
                      </span>
                    )}
                  </div>
                  <div className="text-sm font-semibold text-zinc-300">
                    {result.matchType === 'rank' ? '랭크' : result.matchType === 'normal' ? '일반' : ''}
                    {result.outcome?.includes('탈출') && <span className="ml-1 text-amber-300">탈출</span>}
                  </div>
                </div>
                {canCorrect && (
                  <button
                    type="button"
                    className="text-zinc-500 opacity-0 hover:text-sky-300 group-hover/result:opacity-100"
                    title="순위·결과 보정"
                    onClick={(e) => {
                      e.stopPropagation()
                      setEditing(true)
                    }}
                  >
                    ✎
                  </button>
                )}
              </div>
            ) : (
              <div className="group/result flex items-start gap-1">
                <div>
                  <div className="text-base font-semibold text-zinc-400">게임 {group.number}</div>
                  <div className="text-xs text-zinc-500">결과 미확인</div>
                </div>
                {canCorrect && (
                  <button
                    type="button"
                    className="text-zinc-500 opacity-0 hover:text-sky-300 group-hover/result:opacity-100"
                    title="순위·결과 보정"
                    onClick={(e) => {
                      e.stopPropagation()
                      setEditing(true)
                    }}
                  >
                    ✎
                  </button>
                )}
              </div>
            )}
          </div>

          <div className={timeLabel ? 'w-44 text-sm' : 'w-28 text-sm'}>
            <div className="text-zinc-200">{timeLabel ? timeLabel.main : formatStart(group.matchStartUtc)}</div>
            <div className="text-xs text-zinc-500">{timeLabel ? timeLabel.sub : formatAgo(group.matchStartUtc)}</div>
          </div>

          <PortraitRow clip={group.clips[0]} />

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
        </div>
        <div className="flex shrink-0 items-center gap-3 px-3 text-xs">
          {group.recordId ? (
            <button type="button" className="text-zinc-400 hover:text-rose-400" onClick={onDeleteRecord}>
              기록 삭제
            </button>
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
              <button type="button" className="text-zinc-400 hover:text-rose-400" onClick={onDeleteGame}>
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

      {reprocessing && (
        <div className="border-t border-zinc-700 bg-sky-950/30 px-4 py-2">
          <div className="h-1.5 overflow-hidden rounded bg-zinc-700">
            <div className="indeterminate-bar h-full rounded bg-sky-500" />
          </div>
          <p className="mt-1 text-xs text-sky-300">다시 분석하는 중입니다. 원본 녹화에서 클립을 새로 만들고 있습니다.</p>
        </div>
      )}

      {expanded && (
        <div
          className={`border-t border-zinc-700 p-4 ${bare ? '' : 'grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4'}`}
        >
          {children}
        </div>
      )}
    </section>
  )
}
