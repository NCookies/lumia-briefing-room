import { useCallback, useEffect, useMemo, useState } from 'react'
import { dayAnchorId, dayId } from '../dayFold'
import { groupByDay } from '../gameDays'
import type { GameSummary } from '../games'
import { getGames, setGamePinned } from '../gamesApi'
import { onlyDueGames } from '../cleanupPreview'
import { formatAgo } from '../grouping'
import { formatBytes } from '../retention'
import { useCleanupPreview } from '../useCleanupPreview'
import { useStorageUsage } from '../useStorageUsage'
import { useDayFold } from '../useDayFold'
import { useGameDelete } from '../useGameDelete'
import { useRebuildFullVideo } from '../useRebuildFullVideo'
import type { DeleteMode } from '../deleteConfirm'
import { DueOnlyToggle } from './DueOnlyToggle'
import { GameDayHeader } from './GameDayHeader'
import { GameRow } from './GameRow'
import { GameViewer } from './GameViewer'
import { StorageUsageBar } from './StorageUsageBar'

function formatShort(iso: string | null): string {
  if (!iso) return '시각 미상'
  const d = new Date(iso)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${d.getMonth() + 1}/${d.getDate()} ${hh}:${mm}`
}

interface Props {
  active: boolean
  refreshTick: number
  onBackfill: () => void
  backfillLabel: string
  confirmDelete: boolean
  onConfirmDeleteChange: (value: boolean) => void
  deleteMode: DeleteMode
  onDeleteModeChange: (value: DeleteMode) => void
}

export function GameList({
  active,
  refreshTick,
  onBackfill,
  backfillLabel,
  confirmDelete,
  onConfirmDeleteChange,
  deleteMode,
  onDeleteModeChange,
}: Props) {
  const [games, setGames] = useState<GameSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const [dueOnly, setDueOnly] = useState(false)
  const cleanup = useCleanupPreview(active)
  const storage = useStorageUsage(active, games)
  const shown = useMemo(() => onlyDueGames(games ?? [], cleanup, dueOnly), [games, cleanup, dueOnly])
  const dueCount = useMemo(() => onlyDueGames(games ?? [], cleanup, true).length, [games, cleanup])
  const dayGroups = useMemo(
    () => groupByDay(shown.map((g) => ({ ...g, matchStartUtc: g.matchStartUtc ?? '' }))),
    [shown],
  )
  const dayList = useMemo(() => dayGroups.map((d) => d.day), [dayGroups])
  const fold = useDayFold('steam', dayList)

  const load = useCallback(() => {
    getGames()
      .then(setGames)
      .catch((e: Error) => setError(e.message))
  }, [])
  const rebuild = useRebuildFullVideo(load)
  const gameDelete = useGameDelete({
    confirmDelete,
    onConfirmDeleteChange,
    deleteMode,
    onDeleteModeChange,
    onDone: load,
    onError: setError,
  })
  const viewerDelete = useGameDelete({
    confirmDelete,
    onConfirmDeleteChange,
    deleteMode,
    onDeleteModeChange,
    onDone: () => {
      setOpen(null)
      load()
    },
    onError: setError,
  })

  useEffect(() => {
    if (active) load()
  }, [active, load, refreshTick])

  if (open) {
    const summary = games?.find((g) => g.key === open)
    return (
      <>
        <GameViewer gameKey={open} onBack={() => setOpen(null)} onChanged={load} menu={summary && viewerDelete.menuFor(open, summary)} />
        {viewerDelete.dialog}
      </>
    )
  }

  if (!games) return <p className="p-4 text-sm text-zinc-400">{error ?? '불러오는 중…'}</p>

  const total = games.reduce((sum, g) => sum + (g.fullVideoSizeBytes ?? 0), 0)

  return (
    <div className="flex flex-1 flex-col gap-2 p-4">
      <div className="flex items-baseline gap-3 text-sm text-zinc-300">
        <span>게임 {dueOnly ? `${shown.length} / ${games.length}` : games.length}개</span>
        <StorageUsageBar totals={storage} tabBytes={total} />
        {!(storage && storage.autoCleanEnabled && storage.limitGb) && (
          <span className="text-xs text-zinc-500">풀영상 {formatBytes(total)}</span>
        )}
        {games.length > 0 && (
          <>
            <button
              type="button"
              className="rounded border border-zinc-600 px-2 py-0.5 text-xs hover:bg-zinc-700 disabled:opacity-40"
              disabled={fold.collapsed.size === 0}
              onClick={fold.expandAll}
            >
              날짜 모두 펼치기
            </button>
            <button
              type="button"
              className="rounded border border-zinc-600 px-2 py-0.5 text-xs hover:bg-zinc-700 disabled:opacity-40"
              disabled={fold.allCollapsed}
              onClick={fold.collapseAll}
            >
              날짜 모두 접기
            </button>
          </>
        )}
        <DueOnlyToggle checked={dueOnly} count={dueCount} onChange={setDueOnly} />
        <button
          type="button"
          className="ml-auto rounded border border-zinc-600 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-700"
          title="게임 로그에 남지 않은 과거 녹화에서 게임을 찾아 만듭니다"
          onClick={onBackfill}
        >
          {backfillLabel}
        </button>
      </div>
      {dueOnly && shown.length === 0 && <p className="text-sm text-zinc-500">삭제 예정인 게임이 없습니다.</p>}
      {games.length === 0 && (
        <p className="text-sm text-zinc-500">
          아직 처리한 게임이 없습니다. 게임을 한 판 마치면 전체 영상과 교전 후보가 여기에 쌓입니다.
        </p>
      )}
      {dayGroups.map((dayGroup) => (
        <section
          key={dayGroup.day ?? 'unknown'}
          id={dayAnchorId('steam', dayGroup.day)}
          className="flex flex-col gap-2 [&+&]:mt-4"
        >
          <GameDayHeader
            day={dayGroup.day}
            gameCount={dayGroup.games.length}
            clipCount={dayGroup.games.reduce((n, g) => n + g.savedClipCount, 0)}
            clipBytes={dayGroup.games.reduce((n, g) => n + (g.fullVideoSizeBytes ?? 0), 0)}
            bytesLabel="풀영상 "
            collapsed={fold.collapsed.has(dayId(dayGroup.day))}
            onToggle={() => fold.toggle(dayGroup.day)}
          />
          {!fold.collapsed.has(dayId(dayGroup.day)) && (
          <ul className="flex flex-col gap-2">
            {dayGroup.games.map((g) => (
              <GameRow
                key={g.key}
                game={g}
                time={{ main: formatShort(g.matchStartUtc), sub: g.matchStartUtc ? formatAgo(g.matchStartUtc) : '' }}
                due={cleanup[g.key]}
                menu={gameDelete.menuFor(g.key, g)}
                onOpen={() => setOpen(g.key)}
                rebuild={
                  g.canRebuildFullVideo && !g.hasFullVideo
                    ? {
                        label: rebuild.running === g.key ? rebuild.state.text ?? '만드는 중…' : '풀영상 만들기',
                        disabled: rebuild.running !== null,
                        onClick: () => rebuild.start(g.key),
                      }
                    : undefined
                }
                onPin={() =>
                  void setGamePinned(g.key, !g.pinned)
                    .then(load)
                    .catch((err: Error) => setError(err.message))
                }
              />
            ))}
          </ul>
          )}
        </section>
      ))}
      {rebuild.state.text && rebuild.running === null && (
        <p className={`text-sm ${rebuild.state.error ? 'text-rose-300' : 'text-emerald-300'}`}>{rebuild.state.text}</p>
      )}
      {error && <p className="text-sm text-rose-300">{error}</p>}
      {gameDelete.dialog}
    </div>
  )
}
