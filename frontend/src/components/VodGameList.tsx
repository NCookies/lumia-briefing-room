import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useConfirm } from '../confirmContext'
import type { DeleteMode } from '../deleteConfirm'
import { onlyDueGames } from '../cleanupPreview'
import { dayAnchorId, dayId } from '../dayFold'
import type { GameSummary } from '../games'
import { getGames, setGamePinned } from '../gamesApi'
import { useGameDelete } from '../useGameDelete'
import { useGameEdit } from '../useGameEdit'
import { formatBytes } from '../retention'
import { useCleanupPreview } from '../useCleanupPreview'
import { useStorageUsage } from '../useStorageUsage'
import { useListScroll } from '../useListScroll'
import type { GameNav } from '../useRoute'
import { useDayFold } from '../useDayFold'
import {
  cancelAnalysis,
  deleteVod,
  deleteVodClips,
  getAnalysis,
  getDeleteSourceAfter,
  listVods,
  setDeleteSourceAfter,
  setStreamer,
  setVideoDate,
  startAnalysis,
  startFullVideos,
  type AnalysisJob,
} from '../vodApi'
import { groupVodsByDate } from '../vodDates'
import { resolvedDeleteSource } from '../vodDeleteSource'
import { vodAnalyzeConfirmMessage, vodDoneNotice } from '../vodAnalyzeConfirm'
import { analysisEnded, buildableGameCount, groupGamesByVod, vodDeleteAllMessage, vodGameTime, vodRemoveMessage, vodTotals } from '../vodGames'
import { probeProgress, type Vod } from '../vodGrouping'
import { DeleteConfirmDialog } from './DeleteConfirmDialog'
import { DueOnlyToggle } from './DueOnlyToggle'
import { GameDayHeader } from './GameDayHeader'
import { GameRow } from './GameRow'
import { GameViewer } from './GameViewer'
import { LoadingBar } from './LoadingBar'
import { StorageUsageBar } from './StorageUsageBar'
import { VideoFormatHelp } from './VideoFormatHelp'
import { VodSection } from './VodSection'

interface DeleteRequest {
  label: string
  run: (mode: DeleteMode) => Promise<unknown>
}

interface Props {
  active: boolean
  nav: GameNav
  refreshTick: number
  confirmDelete: boolean
  onConfirmDeleteChange: (value: boolean) => void
  deleteMode: DeleteMode
  onDeleteModeChange: (value: DeleteMode) => void
  onAddVodSources: () => void
}

/** 영상 파일 탭: 날짜 머리줄 > 영상 묶음(분석·이름·날짜 조작 그대로) > 게임 행(스팀 녹화 탭과 같은 모양) → 게임을 누르면 풀영상 화면. */
export function VodGameList({
  active,
  nav,
  refreshTick,
  confirmDelete,
  onConfirmDeleteChange,
  deleteMode,
  onDeleteModeChange,
  onAddVodSources,
}: Props) {
  const [vods, setVods] = useState<Vod[]>([])
  const [vodsLoaded, setVodsLoaded] = useState(false)
  const [games, setGames] = useState<GameSummary[] | null>(null)
  const [job, setJob] = useState<AnalysisJob | null>(null)
  const open = nav.openKey
  const rememberScroll = useListScroll(open, active)
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [collapsedVods, setCollapsedVods] = useState<Set<string>>(new Set())
  const [deleteRequest, setDeleteRequest] = useState<DeleteRequest | null>(null)
  const ask = useConfirm()
  const [dueOnly, setDueOnly] = useState(false)
  const cleanup = useCleanupPreview(active)
  const storage = useStorageUsage(active, games)
  const shown = useMemo(() => onlyDueGames(games ?? [], cleanup, dueOnly), [games, cleanup, dueOnly])
  const dueCount = useMemo(() => onlyDueGames(games ?? [], cleanup, true).length, [games, cleanup])

  const groups = useMemo(() => {
    const all = groupGamesByVod(vods, shown)
    return dueOnly ? all.filter((g) => g.games.length > 0) : all
  }, [vods, shown, dueOnly])
  const dateGroups = useMemo(() => groupVodsByDate(groups, 'desc'), [groups])
  const days = useMemo(() => dateGroups.map((d) => d.day), [dateGroups])
  const fold = useDayFold('vod', days)

  const reloadGames = useCallback(() => {
    getGames('vod')
      .then(setGames)
      .catch((e: Error) => setError(e.message))
  }, [])

  const reloadVods = useCallback(() => {
    listVods()
      .then(setVods)
      .catch((e: Error) => setError(e.message))
      .finally(() => setVodsLoaded(true))
  }, [])

  const reload = useCallback(() => {
    setError(null)
    reloadVods()
    reloadGames()
  }, [reloadVods, reloadGames])

  useEffect(() => {
    if (active) reload()
  }, [active, reload])

  const handledTick = useRef(refreshTick)
  useEffect(() => {
    if (handledTick.current === refreshTick) return
    handledTick.current = refreshTick
    if (active) reload()
  }, [refreshTick, active, reload])

  const gameDelete = useGameDelete({
    confirmDelete,
    onConfirmDeleteChange,
    deleteMode,
    onDeleteModeChange,
    onDone: reload,
    onError: setActionError,
  })
  const viewerDelete = useGameDelete({
    confirmDelete,
    onConfirmDeleteChange,
    deleteMode,
    onDeleteModeChange,
    onDone: () => {
      nav.close()
      reload()
    },
    onError: setActionError,
  })

  const [viewerTick, setViewerTick] = useState(0)
  const gameEdit = useGameEdit({
    onDone: () => {
      reload()
      setViewerTick((t) => t + 1)
    },
    onError: setActionError,
  })

  const runningVodId = vods.find((v) => v.status === 'analyzing')?.id ?? null
  const probe = probeProgress(vods)

  const lastRunningVodId = useRef(runningVodId)
  useEffect(() => {
    if (analysisEnded(lastRunningVodId.current, runningVodId)) reloadGames()
    lastRunningVodId.current = runningVodId
  }, [runningVodId, reloadGames])

  useEffect(() => {
    if (!active || !probe.active) return
    const timer = setInterval(() => {
      listVods()
        .then(setVods)
        .catch(() => {})
    }, 2000)
    return () => clearInterval(timer)
  }, [active, probe.active])

  const hasQueuedVod = vods.some((v) => v.status === 'queued')
  useEffect(() => {
    if (!active || (runningVodId === null && !hasQueuedVod)) return
    const timer = setInterval(async () => {
      try {
        if (runningVodId === null) {
          setVods(await listVods())
          return
        }
        const status = await getAnalysis(runningVodId)
        setJob(status)
        setVods(await listVods())
        if (status.state === 'running') return
        if (status.state === 'error') setActionError(status.message ?? '작업에 실패했습니다')
        if (status.state === 'done') setNotice(vodDoneNotice(status))
        reloadGames()
      } catch (e) {
        setActionError((e as Error).message)
      }
    }, 2000)
    return () => clearInterval(timer)
  }, [active, runningVodId, hasQueuedVod, reloadGames])

  const runAndReload = async (action: () => Promise<unknown>) => {
    setActionError(null)
    try {
      await action()
    } catch (e) {
      setActionError((e as Error).message)
    } finally {
      reload()
    }
  }

  const requestDelete = (label: string, run: (mode: DeleteMode) => Promise<unknown>) => {
    if (!confirmDelete) {
      void runAndReload(() => run(deleteMode))
      return
    }
    setDeleteRequest({ label, run })
  }

  const handleDeleteConfirm = async ({ mode, skipNext }: { mode: DeleteMode; skipNext: boolean }) => {
    const request = deleteRequest
    setDeleteRequest(null)
    if (skipNext) onConfirmDeleteChange(false)
    if (mode !== deleteMode) onDeleteModeChange(mode)
    if (request) await runAndReload(() => request.run(mode))
  }

  const handleAnalyze = async (vod: Vod, options: { force?: boolean; rebuild?: boolean }) => {
    const fromFull = !vod.exists && vod.canReanalyzeFromFullVideos === true
    const result = await ask({
      message: vodAnalyzeConfirmMessage(vod.name, options, fromFull),
      confirmLabel: options.force ? '다시 분석' : options.rebuild ? '다시 만들기' : '분석 시작',
    })
    if (!result.ok) return

    if (fromFull) {
      setActionError(null)
      setNotice(null)
      try {
        await startAnalysis(vod.id, {})
        reloadVods()
      } catch (e) {
        setActionError((e as Error).message)
      }
      return
    }

    let deleteSource = resolvedDeleteSource(await getDeleteSourceAfter())
    if (deleteSource === null) {
      const choice = await ask({
        message: '게임 풀영상 저장이 끝나면 원본 영상 파일을 삭제할까요?',
        confirmLabel: '삭제',
        cancelLabel: '삭제 안 함',
        allowSkip: true,
        danger: true,
      })
      deleteSource = choice.ok
      if (choice.skipNext) await setDeleteSourceAfter(choice.ok ? 'always' : 'never')
    }

    setActionError(null)
    setNotice(null)
    try {
      await startAnalysis(vod.id, { ...options, deleteSource })
      reloadVods()
    } catch (e) {
      setActionError((e as Error).message)
    }
  }

  const handleBuildFullVideos = async (vod: Vod, count: number) => {
    const size = vod.sizeBytes ? `디스크를 최대 ${formatBytes(vod.sizeBytes)}(원본 크기) 안에서 새로 씁니다.` : ''
    const result = await ask({
      message: `"${vod.name}" 에서 이전 버전에 분석한 게임 ${count}개의 풀영상을 원본에서 잘라 만듭니다.\n원본 영상은 그대로 두고, 저장해 둔 클립은 다시 만들지 않습니다. ${size}\n게임마다 결과 화면·초상화를 다시 찾아 몇 분 걸립니다(게임 하나에 30초~1분). 계속하시겠습니까?`,
      confirmLabel: '풀영상 만들기',
    })
    if (!result.ok) return
    setActionError(null)
    setNotice(null)
    try {
      await startFullVideos(vod.id)
      reloadVods()
    } catch (e) {
      setActionError((e as Error).message)
    }
  }

  const handleCancel = (vod: Vod) =>
    cancelAnalysis(vod.id)
      .then(reloadVods)
      .catch((e: Error) => setActionError(e.message))

  const handleRenameStreamer = (vod: Vod, name: string) =>
    setStreamer(vod.id, name)
      .then(reloadVods)
      .catch((e: Error) => setActionError(e.message))

  const handleEditVideoDate = (vod: Vod, date: string) =>
    setVideoDate(vod.id, date)
      .then(reloadVods)
      .catch((e: Error) => setActionError(e.message))

  const handleDeleteAll = (vod: Vod, name: string, totals: ReturnType<typeof vodTotals>) =>
    requestDelete(vodDeleteAllMessage(name, totals.games, totals.autoClips, totals.clips), () => deleteVodClips(vod.id))

  const handleRemoveVod = async (id: string, name: string, keptClips: number) => {
    const result = await ask({
      message: vodRemoveMessage(name, keptClips),
      confirmLabel: '목록에서 삭제',
      danger: true,
    })
    if (result.ok) await runAndReload(() => deleteVod(id))
  }

  if (open) {
    const summary = games?.find((g) => g.key === open)
    return (
      <>
        <GameViewer key={`${open}-${viewerTick}`} gameKey={open} autoPlay={nav.userOpened} onMissing={nav.missing} backLabel="← 영상 목록" onBack={nav.close} onChanged={reloadGames} menu={summary && viewerDelete.menuFor(open, summary, [gameEdit.menuItem(open, summary)])} />
        {viewerDelete.dialog}
        {gameEdit.dialog}
      </>
    )
  }

  const allGames = games ?? []
  const total = vodTotals(allGames)
  const empty = vodsLoaded && games !== null && groups.length === 0 && !dueOnly

  return (
    <div className="flex flex-1 flex-col gap-2 p-4">
      <div className="flex flex-wrap items-baseline gap-3 text-sm text-zinc-300">
        <span>게임 {dueOnly ? `${shown.length} / ${allGames.length}` : total.games}개</span>
        <StorageUsageBar totals={storage} tabBytes={total.bytes} />
        {!(storage && storage.autoCleanEnabled && storage.limitGb) && (
          <span className="text-xs text-zinc-500">풀영상 {formatBytes(total.bytes)}</span>
        )}
        {days.length > 0 && (
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
        <VideoFormatHelp />
        <button
          type="button"
          className="ml-auto rounded border border-zinc-600 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-700"
          title="영상 파일 목록과 분석 결과를 다시 읽습니다"
          onClick={reload}
        >
          새로고침
        </button>
      </div>

      {(!vodsLoaded || games === null) && !error && <LoadingBar label="영상 파일 목록을 불러오는 중입니다…" />}
      {vodsLoaded && probe.active && (
        <div className="rounded border border-zinc-700 bg-zinc-800/60 p-3">
          <LoadingBar
            label={`영상 정보를 읽는 중입니다 (${probe.done}/${probe.total})`}
            detail="용량이 큰 영상은 길이를 읽는 데 1분 넘게 걸릴 수 있습니다. 그동안에도 다른 화면은 쓸 수 있고, 끝나면 목록이 자동으로 채워집니다."
            percent={probe.percent}
          />
        </div>
      )}
      {error && <p className="text-sm text-rose-400">오류가 발생했습니다: {error}</p>}
      {actionError && <p className="text-sm text-rose-400">{actionError}</p>}
      {notice && <p className="text-sm text-emerald-400">{notice}</p>}

      {dueOnly && groups.length === 0 && <p className="text-sm text-zinc-500">삭제 예정인 게임이 없습니다.</p>}

      {empty && (
        <div className="flex min-h-[50vh] flex-col items-center justify-center gap-3 text-center text-zinc-400">
          <p className="text-base text-zinc-300">분석할 영상 파일이 없습니다. 영상 파일이나 폴더를 추가해 주세요</p>
          <button
            type="button"
            className="rounded border border-sky-500/60 px-4 py-1.5 text-sm text-sky-300 hover:bg-sky-500/20"
            onClick={onAddVodSources}
          >
            영상 경로 추가
          </button>
          <span className="flex items-center gap-1.5 text-xs text-zinc-500">
            어떤 영상을 넣을 수 있나요?
            <VideoFormatHelp centered />
          </span>
        </div>
      )}

      <div className="flex flex-col gap-3">
        {dateGroups.map((dateGroup) => (
          <section key={dateGroup.day ?? 'unknown'} id={dayAnchorId('vod', dateGroup.day)} className="flex flex-col gap-3 [&+&]:mt-5">
            <GameDayHeader
              day={dateGroup.day}
              videoCount={dateGroup.vods.length}
              gameCount={dateGroup.vods.reduce((n, vg) => n + vg.games.length, 0)}
              clipCount={dateGroup.vods.reduce((n, vg) => n + vodTotals(vg.games).clips, 0)}
              clipBytes={dateGroup.vods.reduce((n, vg) => n + vodTotals(vg.games).bytes, 0)}
              bytesLabel="풀영상 "
              collapsed={fold.collapsed.has(dayId(dateGroup.day))}
              onToggle={() => fold.toggle(dateGroup.day)}
            />
            {!fold.collapsed.has(dayId(dateGroup.day)) &&
              dateGroup.vods.map((vg) => {
                const totals = vodTotals(vg.games)
                const buildable = buildableGameCount(vg.games)
                const vod = vg.vod
                return (
                  <VodSection
                    key={vg.vodId}
                    name={vg.name}
                    vod={vod}
                    job={job?.id === vg.vodId ? job : null}
                    expanded={!collapsedVods.has(vg.vodId)}
                    gameCount={totals.games}
                    clipCount={totals.clips}
                    visibleGameCount={vg.games.length}
                    clipBytes={totals.bytes}
                    bytesLabel="풀영상 "
                    deletable={vg.games.length > 0 || (vod?.clipCount ?? 0) > 0}
                    emptyHint={
                      vod?.status === 'done'
                        ? '이 영상에서 찾은 게임이 없습니다'
                        : '아직 게임이 없습니다. 분석을 시작하면 게임별로 풀영상이 만들어집니다.'
                    }
                    buildableCount={buildable}
                    onBuildFullVideos={() => vod && handleBuildFullVideos(vod, buildable)}
                    onToggle={() =>
                      setCollapsedVods((prev) => {
                        const next = new Set(prev)
                        if (!next.delete(vg.vodId)) next.add(vg.vodId)
                        return next
                      })
                    }
                    onAnalyze={(options) => vod && handleAnalyze(vod, options)}
                    onCancel={() => vod && handleCancel(vod)}
                    onRenameStreamer={(name) => vod && handleRenameStreamer(vod, name)}
                    onEditDate={(date) => vod && handleEditVideoDate(vod, date)}
                    onDeleteClips={() => vod && handleDeleteAll(vod, vg.name, totals)}
                    onDeleteVod={() => handleRemoveVod(vg.vodId, vg.name, totals.clips)}
                  >
                    <ul className="flex flex-col gap-2">
                      {vg.games.map((g) => (
                        <GameRow
                          key={g.key}
                          game={g}
                          time={vodGameTime(g)}
                          menu={gameDelete.menuFor(g.key, g, [gameEdit.menuItem(g.key, g)])}
                          onRename={(title) => void gameEdit.saveTitle(g.key, title)}
                          due={cleanup[g.key]}
                          onOpen={() => {
                            rememberScroll()
                            nav.open(g.key)
                          }}
                          onPin={() =>
                            void setGamePinned(g.key, !g.pinned)
                              .then(reloadGames)
                              .catch((err: Error) => setActionError(err.message))
                          }
                        />
                      ))}
                    </ul>
                  </VodSection>
                )
              })}
          </section>
        ))}
      </div>

      {gameDelete.dialog}
      {gameEdit.dialog}
      {deleteRequest && (
        <DeleteConfirmDialog
          label={deleteRequest.label}
          deleteMode={deleteMode}
          onCancel={() => setDeleteRequest(null)}
          onConfirm={handleDeleteConfirm}
        />
      )}
    </div>
  )
}
