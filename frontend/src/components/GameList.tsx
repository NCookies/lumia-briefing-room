import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { dayAnchorId, dayId } from '../dayFold'
import { groupByDay } from '../gameDays'
import type { GameSummary } from '../games'
import { getGames, setGamePinned } from '../gamesApi'
import { onlyDueGames } from '../cleanupPreview'
import { formatAgo } from '../grouping'
import { formatBytes } from '../retention'
import { useCleanupPreview } from '../useCleanupPreview'
import { useStorageUsage } from '../useStorageUsage'
import { useListScroll } from '../useListScroll'
import { returnedToList } from '../listLoad'
import type { GameNav } from '../useRoute'
import { useDayFold } from '../useDayFold'
import { useGameDelete } from '../useGameDelete'
import { useGameEdit } from '../useGameEdit'
import { useConfirm } from '../confirmContext'
import { reanalyzeConfirmMessage } from '../reanalyze'
import { useGameJobs } from '../useGameJobs'
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
  nav: GameNav
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
  nav,
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
  const open = nav.openKey
  const rememberScroll = useListScroll(open, active)
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
  const [viewerTick, setViewerTick] = useState(0)
  const jobs = useGameJobs(
    useCallback(() => {
      load()
      setViewerTick((t) => t + 1)
    }, [load]),
  )
  const gameEdit = useGameEdit({
    onDone: () => {
      load()
      setViewerTick((t) => t + 1)
    },
    onError: setError,
  })
  const ask = useConfirm()
  const reanalyzeItem = (key: string) => ({
    label: '다시 분석',
    disabled: key in jobs.jobs,
    title: '원본 녹화가 남아 있으면 풀영상·후보·결과표·초상화를 전부 다시 만들고, 없으면 풀영상에서 후보만 다시 찾습니다',
    onSelect: async () => {
      try {
        const mode = await jobs.plan(key)
        if (mode === null) return jobs.fail(key, '원본 녹화도 풀영상도 남아 있지 않아 다시 분석할 수 없습니다')
        const answer = await ask({ message: reanalyzeConfirmMessage(), confirmLabel: '다시 분석' })
        if (answer.ok) jobs.startReanalysis(key)
      } catch (e) {
        jobs.fail(key, (e as Error).message)
      }
    },
  })
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
      nav.close()
      load()
    },
    onError: setError,
  })

  useEffect(() => {
    if (active) load()
  }, [active, load, refreshTick])

  const prevOpen = useRef(open)
  useEffect(() => {
    if (returnedToList(prevOpen.current, open)) load()
    prevOpen.current = open
  }, [open, load])

  if (open) {
    const summary = games?.find((g) => g.key === open)
    return (
      <>
        <GameViewer key={`${open}-${viewerTick}`} active={active} gameKey={open} initialSelected={nav.openCand} backLabel={nav.backLabel} autoPlay={viewerTick === 0 && nav.userOpened} onMissing={nav.missing} onBack={nav.close} onChanged={load} menu={summary && viewerDelete.menuFor(open, summary, [gameEdit.menuItem(open, summary), reanalyzeItem(open)])} />
        {viewerDelete.dialog}
        {gameEdit.dialog}
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
              className="rounded-md border border-zinc-600/70 px-2 py-0.5 text-xs transition hover:bg-zinc-700 disabled:opacity-40"
              disabled={fold.collapsed.size === 0}
              onClick={fold.expandAll}
            >
              날짜 모두 펼치기
            </button>
            <button
              type="button"
              className="rounded-md border border-zinc-600/70 px-2 py-0.5 text-xs transition hover:bg-zinc-700 disabled:opacity-40"
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
          className="ml-auto rounded-md border border-zinc-600/70 px-2 py-1 text-xs text-zinc-300 transition hover:bg-zinc-700"
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
                menu={gameDelete.menuFor(g.key, g, [gameEdit.menuItem(g.key, g), reanalyzeItem(g.key)])}
                onRename={(title) => void gameEdit.saveTitle(g.key, title)}
                onOpen={() => {
                  rememberScroll()
                  nav.open(g.key)
                }}
                job={
                  jobs.jobs[g.key]
                    ? { text: jobs.jobs[g.key].text, queued: jobs.jobs[g.key].state === 'queued', onCancel: () => void jobs.cancel(g.key) }
                    : undefined
                }
                rebuild={
                  g.canRebuildFullVideo && !g.hasFullVideo
                    ? {
                        label: '풀영상 만들기',
                        disabled: g.key in jobs.jobs,
                        onClick: () => jobs.startRebuild(g.key),
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
      {jobs.result && (
        <p className={`text-sm ${jobs.result.error ? 'text-rose-300' : 'text-emerald-300'}`}>{jobs.result.text}</p>
      )}
      {error && <p className="text-sm text-rose-300">{error}</p>}
      {gameDelete.dialog}
      {gameEdit.dialog}
    </div>
  )
}
