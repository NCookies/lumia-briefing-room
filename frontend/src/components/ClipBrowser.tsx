import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { gameCleanupEntry } from '../cleanupPreview'
import { useCleanupPreview } from '../useCleanupPreview'
import {
  deleteClip,
  deleteGameRecord,
  gameRecordImageUrl,
  listGameRecords,
  resultImageUrl,
  getReprocessStatus,
  listClips,
  patchClip,
  startReprocess,
  splitClip,
  trimClip,
} from '../api'
import { useConfirm } from '../confirmContext'
import type { DeleteMode } from '../deleteConfirm'
import { ClipCard } from './ClipCard'
import { DeleteConfirmDialog } from './DeleteConfirmDialog'
import { DEFAULT_FILTER, FilterBar, type FilterState } from './FilterBar'
import { ExportDialog } from './ExportDialog'
import { GameSection } from './GameSection'
import { GameDayHeader } from './GameDayHeader'
import { groupByDay } from '../gameDays'
import { PlayerModal } from './PlayerModal'
import { ResultCard, ResultViewer } from './ResultCard'
import { GameTimeline } from './GameTimeline'
import { VodSection } from './VodSection'
import { VideoFormatHelp } from './VideoFormatHelp'
import { LoadingBar } from './LoadingBar'
import { LabelingHelp } from './LabelingHelp'
import { emptyStateKind } from '../emptyState'
import { loadViewMode, saveViewMode, type ViewMode } from '../viewMode'
import {
  formatMatchResult,
  groupByGame,
  resultImageRef,
  totalSize,
  withResultImage,
  type GameGroup,
} from '../grouping'
import { applyLabel, applyNote, progress } from '../labeling'
import { useLabelingUi } from '../labelingContext'
import { formatBytes } from '../retention'
import type { Clip, GameRecord, UserLabel } from '../types'
import {
  cancelAnalysis,
  deleteVod,
  deleteVodClips,
  deleteVodGame,
  getAnalysis,
  getDeleteSourceAfter,
  listVods,
  setDeleteSourceAfter,
  setStreamer,
  setVideoDate,
  startAnalysis,
  vodGameResultImageUrl,
  type AnalysisJob,
} from '../vodApi'
import { groupVodsByDate } from '../vodDates'
import { dayAnchorId, dayId, shortcutDays } from '../dayFold'
import { useDayFold } from '../useDayFold'
import { DayShortcutBar } from './DayShortcutBar'
import { resolvedDeleteSource } from '../vodDeleteSource'
import { formatDuration, formatGameRange, groupByVod, probeProgress, type Vod } from '../vodGrouping'

function resolveResultImageUrl(group: { recordId?: string; clips: { id: string }[]; key: string; number: number }): string {
  const ref = resultImageRef(group)
  if (ref.kind === 'record') return gameRecordImageUrl(ref.id)
  if (ref.kind === 'clip') return resultImageUrl(ref.id)
  return vodGameResultImageUrl(ref.vodId, ref.index)
}

export type ClipSource = 'steam' | 'vod'

const EMPTY_TITLES: Record<string, string> = {
  filter: '조건에 맞는 클립이 없습니다',
  steam: '아직 클립이 없습니다',
  'vod-no-sources': '분석할 영상 파일이 없습니다. 영상 파일이나 폴더를 추가해 주세요',
  'vod-no-clips': '표시할 클립이 없습니다',
}
const EMPTY_HINTS: Record<string, string> = {
  filter: '필터를 풀면 나올 수 있습니다.',
  steam: '게임이 끝나면 자동으로 만들어집니다. 이미 녹화해 둔 영상은 과거 녹화 분석으로 찾을 수 있습니다.',
  'vod-no-clips': '영상 파일을 분석하면 게임별로 만들어집니다. 다른 영상은 옵션 → 영상 파일에서 추가할 수 있습니다.',
}

const filterActive = (f: FilterState): boolean =>
  f.pinnedOnly ||
  f.cleanupOnly ||
  f.tags.length > 0 ||
  f.gameMode !== '' ||
  f.label !== '' ||
  f.minPvpScore > 0 ||
  f.q.trim() !== ''

interface DeleteRequest {
  label: string
  run: (mode: DeleteMode) => Promise<unknown>
}

interface Props {
  source: ClipSource
  active: boolean
  confirmDelete: boolean
  onConfirmDeleteChange: (value: boolean) => void
  deleteMode: DeleteMode
  onDeleteModeChange: (value: DeleteMode) => void
  onBackfill: () => void
  backfillLabel: string
  onAddVodSources: () => void
  refreshTick: number
}

export function ClipBrowser({
  source,
  active,
  confirmDelete,
  onConfirmDeleteChange,
  deleteMode,
  onDeleteModeChange,
  onBackfill,
  backfillLabel,
  onAddVodSources,
  refreshTick,
}: Props) {
  const [filter, setFilter] = useState<FilterState>(source === 'vod' ? { ...DEFAULT_FILTER, sort: 'asc' } : DEFAULT_FILTER)
  const labeling = useLabelingUi()
  const cleanupPreview = useCleanupPreview(source === 'steam')
  useEffect(() => {
    if (!labeling) setFilter((f) => (f.label === '' ? f : { ...f, label: '' }))
  }, [labeling])
  const [clips, setClips] = useState<Clip[]>([])
  const [records, setRecords] = useState<GameRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [exportTarget, setExportTarget] = useState<Clip | null>(null)
  const [resultViewKey, setResultViewKey] = useState<string | null>(null)
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set())
  const [vods, setVods] = useState<Vod[]>([])
  const [vodsLoaded, setVodsLoaded] = useState(source !== 'vod')
  const [job, setJob] = useState<AnalysisJob | null>(null)
  const [collapsedVods, setCollapsedVods] = useState<Set<string>>(new Set())
  const [playingId, setPlayingId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [reprocessKey, setReprocessKey] = useState<string | null>(null)
  const [reprocessGame, setReprocessGame] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<ViewMode>(() => loadViewMode(source))
  const [deleteRequest, setDeleteRequest] = useState<DeleteRequest | null>(null)
  const ask = useConfirm()

  const [debouncedQuery, setDebouncedQuery] = useState(filter.q)
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(filter.q), 300)
    return () => clearTimeout(timer)
  }, [filter.q])

  const appliedFilter = useMemo(() => ({ ...filter, q: debouncedQuery }), [filter, debouncedQuery])

  const {
    tags: filterTags, gameMode: filterGameMode, pinnedOnly: filterPinnedOnly,
    minPvpScore: filterMinPvpScore, label: filterLabel,
  } = filter

  const reload = useCallback((silent = false) => {
    if (!silent) {
      setLoading(true)
      setError(null)
    }
    listClips({
      tags: filterTags,
      gameMode: filterGameMode || undefined,
      pinned: filterPinnedOnly || undefined,
      minPvpScore: filterMinPvpScore || undefined,
      label: filterLabel || undefined,
      q: debouncedQuery || undefined,
      source,
    })
      .then(setClips)
      .catch((e: Error) => {
        if (!silent) setError(e.message)
      })
      .finally(() => setLoading(false))
    if (source === 'steam' && !filterActive(appliedFilter)) {
      listGameRecords()
        .then(setRecords)
        .catch(() => setRecords([]))
    } else {
      setRecords([])
    }
  }, [
    filterTags, filterGameMode, filterPinnedOnly, filterMinPvpScore, filterLabel,
    debouncedQuery, source, appliedFilter,
  ])

  useEffect(() => {
    if (active) reload()
  }, [active, reload])

  const handledTick = useRef(refreshTick)

  const reloadVods = useCallback(() => {
    if (source !== 'vod') return
    listVods()
      .then(setVods)
      .catch((e: Error) => setError(e.message))
      .finally(() => setVodsLoaded(true))
  }, [source])

  useEffect(() => {
    if (active) reloadVods()
  }, [active, reloadVods])

  useEffect(() => {
    if (handledTick.current === refreshTick) return
    handledTick.current = refreshTick
    if (!active) return
    reload(true)
    reloadVods()
  }, [refreshTick, active, reload, reloadVods])

  const runningVodId = vods.find((v) => v.status === 'analyzing')?.id ?? null
  const probe = probeProgress(vods)

  useEffect(() => {
    if (!active || source !== 'vod' || !probe.active) return
    const timer = setInterval(() => {
      listVods()
        .then(setVods)
        .catch(() => {})
    }, 2000)
    return () => clearInterval(timer)
  }, [active, source, probe.active])

  useEffect(() => {
    if (!active || source !== 'vod' || runningVodId === null) return
    const timer = setInterval(async () => {
      try {
        const status = await getAnalysis(runningVodId)
        setJob(status)
        setVods(await listVods())
        if (status.state === 'running') return
        if (status.state === 'error') setActionError(status.message ?? '분석에 실패했습니다')
        if (status.state === 'done') setNotice('분석을 마쳤습니다.')
        reload()
      } catch (e) {
        setActionError((e as Error).message)
      }
    }, 2000)
    return () => clearInterval(timer)
  }, [active, source, runningVodId, reload])

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

  const runAll = async (clipsToHandle: Clip[], action: (id: string) => Promise<void>) => {
    const results = await Promise.allSettled(clipsToHandle.map((c) => action(c.id)))
    const failed = results.filter((r): r is PromiseRejectedResult => r.status === 'rejected')
    if (failed.length > 0) {
      throw new Error(`클립 ${failed.length}개를 처리하지 못했습니다. ${(failed[0].reason as Error).message}`)
    }
  }

  const requestDelete = (label: string, run: (mode: DeleteMode) => Promise<unknown>) => {
    if (!confirmDelete) {
      runAndReload(() => run(deleteMode))
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

  const handleTogglePin = (clip: Clip) => runAndReload(() => patchClip(clip.id, { pinned: !clip.pinned }))

  const handleRename = (clip: Clip, title: string) => runAndReload(() => patchClip(clip.id, { title }))

  const handleDelete = (clip: Clip) => requestDelete(`"${clip.title}" 클립을 삭제합니다.`, () => deleteClip(clip.id))

  const gameLabel = (group: GameGroup<Clip>) =>
    `게임 ${group.number}(${group.clips.length}개, ${formatBytes(totalSize(group.clips))})`

  const handleDeleteGame = (group: GameGroup<Clip>) =>
    requestDelete(`${gameLabel(group)}의 클립을 모두 삭제합니다.`, () =>
      // VOD 는 클립이 0개인 게임도 있다(교전은 못 뽑았지만 결과 화면은 읽은 경우,
      // plan.md §10-6) - 클립 기준 삭제(runAll)로는 지울 방법이 없어 게임 요약 자체를
      // 지우는 전용 API 를 쓴다(실사용 보고: "게임 삭제"를 눌러도 목록에서 안 없어짐).
      source === 'vod' && group.clips.length === 0
        ? deleteVodGame(group.key.split('|')[0], group.number)
        : runAll(group.clips, deleteClip),
    )

  const handleCorrectMatchResult = (group: GameGroup<Clip>, values: { placement: number; outcome: string }) =>
    runAndReload(() =>
      runAll(group.clips, (id) => patchClip(id, { matchResult: values }).then(() => undefined)),
    )

  const handleUnlockMatchResult = (group: GameGroup<Clip>) =>
    runAndReload(() =>
      runAll(group.clips, (id) => patchClip(id, { matchResultSource: null }).then(() => undefined)),
    )

  useEffect(() => {
    if (reprocessKey === null) return
    const timer = setInterval(() => {
      getReprocessStatus(reprocessKey)
        .then((status) => {
          if (status.state === 'running') return
          setReprocessKey(null)
          setReprocessGame(null)
          if (status.state === 'done') setNotice(`다시 분석했습니다. 새 클립 ${status.clips}개를 만들었습니다.`)
          else setActionError(status.message)
          reload()
        })
        .catch((e: Error) => {
          setReprocessKey(null)
          setReprocessGame(null)
          setActionError(e.message)
        })
    }, 3000)
    return () => clearInterval(timer)
  }, [reprocessKey, reload])

  const handleReprocess = async (group: GameGroup<Clip>) => {
    const result = await ask({
      message: `다음 게임을 원본 녹화에서 다시 분석합니다.\n${gameLabel(group)}\n분석에 성공하면 기존 클립을 지우고 새로 만듭니다(라벨은 그대로 옮겨집니다). 실패하면 기존 클립은 그대로 남습니다.\n분석에는 몇 분이 걸릴 수 있습니다. 계속하시겠습니까?`,
      confirmLabel: '다시 분석',
    })
    if (!result.ok) return
    setActionError(null)
    setNotice(null)
    try {
      const key = await startReprocess(group.clips[0].id)
      setReprocessKey(key)
      setReprocessGame(group.key)
    } catch (e) {
      setActionError((e as Error).message)
    }
  }

  const handleAnalyze = async (vod: Vod, options: { force?: boolean; rebuild?: boolean }) => {
    const message = options.force
      ? `"${vod.name}" 영상을 처음부터 다시 분석합니다.\n분석에 성공하면 기존 클립을 지우고 새로 만듭니다(라벨은 그대로 옮겨집니다). 실패하면 기존 클립은 그대로 남습니다.\n영상 길이에 따라 수십 분이 걸릴 수 있습니다. 계속하시겠습니까?`
      : options.rebuild
        ? `"${vod.name}" 영상의 클립을 저장된 분석 결과로 다시 만듭니다.\n분석에 성공하면 기존 클립을 지우고 새로 만듭니다. 계속하시겠습니까?`
        : `"${vod.name}" 영상을 분석합니다.\n영상 길이에 따라 수십 분이 걸릴 수 있으며, 도중에 취소해도 다음에 이어서 할 수 있습니다. 계속하시겠습니까?`
    const result = await ask({
      message,
      confirmLabel: options.force ? '다시 분석' : options.rebuild ? '다시 만들기' : '분석 시작',
    })
    if (!result.ok) return

    let deleteSource = resolvedDeleteSource(await getDeleteSourceAfter())
    if (deleteSource === null) {
      const choice = await ask({
        message: '클립 추출이 끝나면 원본 영상 파일을 삭제할까요?',
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

  const handleCancelAnalysis = (vod: Vod) =>
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

  const vodAction = (action: () => Promise<unknown>) =>
    runAndReload(async () => {
      await action()
      reloadVods()
    })

  const handleDeleteVod = (id: string, name: string, count: number) =>
    requestDelete(
      `"${name}" 영상의 클립 ${count}개를 모두 삭제합니다. 영상 파일은 지우지 않습니다.`,
      () => vodAction(() => deleteVodClips(id)),
    )

  const handleDeleteRecord = async (group: GameGroup<Clip>) => {
    const result = await ask({
      message: `게임 ${group.number} 의 기록(순위·전적·결과표)을 삭제합니다. 되돌릴 수 없습니다. 계속하시겠습니까?`,
      confirmLabel: '기록 삭제',
      danger: true,
    })
    if (result.ok && group.recordId) await runAndReload(() => deleteGameRecord(group.recordId!))
  }

  // 스팀 녹화의 "기록 삭제"(클립을 다 지워도 남는 결과 요약을 마저 지우는 것)와 같은
  // 자리 - 다시보기는 클립·원본을 다 지워도 색인(.vods/<id>.json)이 남아 목록에서
  // 안 없어졌다(실사용 보고, 2026-09-29). 같은 확인창 스타일로 색인까지 지운다.
  const handleRemoveVod = async (id: string, name: string) => {
    const result = await ask({
      message: `"${name}" 을(를) 다시보기 목록에서 삭제합니다. 남은 클립과 판독 기록도 함께 지워집니다(원본 영상은 지우지 않으며, 아직 있으면 다음에 새 영상으로 다시 나타납니다). 되돌릴 수 없습니다. 계속하시겠습니까?`,
      confirmLabel: '목록에서 삭제',
      danger: true,
    })
    if (result.ok) await vodAction(() => deleteVod(id))
  }

  const handleNote = (clip: Clip, note: string | null) => {
    setClips((prev) => applyNote(prev, clip.id, note))
    patchClip(clip.id, { labelNote: note }).catch((e: Error) => {
      setError(`라벨 메모를 저장하지 못했습니다: ${e.message}`)
      reload()
    })
  }

  const handleLabel = (clip: Clip, label: UserLabel) => {
    setClips((prev) => applyLabel(prev, clip.id, label))
    patchClip(clip.id, { userLabel: label }).catch((e: Error) => {
      setError(`라벨을 저장하지 못했습니다: ${e.message}`)
      reload()
    })
  }

  const steamGroups = useMemo(() => {
    if (source !== 'steam') return []
    const scoped = filter.cleanupOnly ? clips.filter((c) => cleanupPreview[c.id]) : clips
    return groupByGame(scoped, filter.sort, filter.cleanupOnly ? [] : records)
  }, [source, clips, records, filter.sort, filter.cleanupOnly, cleanupPreview])
  const vodGroups = useMemo(
    () =>
      source === 'vod'
        ? groupByVod(clips, vods, filter.sort, true)
        : [],
    [source, clips, vods, filter.sort],
  )
  const vodDateGroups = useMemo(() => groupVodsByDate(vodGroups, filter.sort), [vodGroups, filter.sort])
  const vodDays = useMemo(() => vodDateGroups.map((d) => d.day), [vodDateGroups])
  const dayFold = useDayFold('vod', vodDays)
  const groups = useMemo(
    () => (source === 'steam' ? steamGroups : vodGroups.flatMap((v) => v.games)),
    [source, steamGroups, vodGroups],
  )
  const ordered = useMemo(() => groups.flatMap((g) => g.clips), [groups])
  const resultGames = useMemo(
    () =>
      withResultImage(groups).map((g) => ({
        key: g.key,
        imageUrl: resolveResultImageUrl(g),
        caption: [`게임 ${g.number}`, formatMatchResult(g.result)].filter(Boolean).join(' · '),
      })),
    [groups],
  )
  const resultViewIndex = resultViewKey === null ? -1 : resultGames.findIndex((g) => g.key === resultViewKey)
  const playingIndex = playingId === null ? -1 : ordered.findIndex((c) => c.id === playingId)
  const toggleGame = (key: string) =>
    setExpandedKeys((prev) => {
      const next = new Set(prev)
      if (!next.delete(key)) next.add(key)
      return next
    })

  const { labeled, total } = progress(ordered)

  const renderClipCard = (clip: Clip) => (
    <ClipCard
      key={clip.id}
      clip={clip}
      onPlay={() => setPlayingId(clip.id)}
      onTogglePin={handleTogglePin}
      onRename={handleRename}
      onDelete={handleDelete}
      onLabel={handleLabel}
      onExport={setExportTarget}
      cleanupEntry={cleanupPreview[clip.id]}
    />
  )

  const timeline = viewMode === 'timeline'

  const renderGame = (group: GameGroup<Clip>) => {
    const imageUrl = resolveResultImageUrl(group)
    const lead = group.result?.imagePath && imageUrl ? (
      <ResultCard
        imageUrl={imageUrl}
        result={group.result}
        onOpen={() => setResultViewKey(group.key)}
      />
    ) : null
    return (
    <GameSection
      key={group.key}
      bare={timeline}
              group={group}
              expanded={expandedKeys.has(group.key)}
              onToggle={() => toggleGame(group.key)}
              onDeleteGame={() => handleDeleteGame(group)}
              onReprocess={() => handleReprocess(group)}
              onDeleteRecord={() => handleDeleteRecord(group)}
              reprocessing={reprocessGame === group.key}
              reprocessBusy={reprocessKey !== null}
              hideReprocess={source === 'vod'}
              matchResultLocked={group.clips[0]?.matchResultSource === 'manual'}
              onCorrectMatchResult={(values) => handleCorrectMatchResult(group, values)}
              onUnlockMatchResult={() => handleUnlockMatchResult(group)}
              cleanupEntry={gameCleanupEntry(group.clips.map((c) => c.id), cleanupPreview)}
              timeLabel={
                source === 'vod' && group.startSec !== undefined
                  ? {
                      main: formatGameRange(group.startSec, group.endSec ?? group.startSec),
                      sub: group.endSec !== undefined ? formatDuration(group.endSec - group.startSec) : undefined,
                    }
                  : undefined
              }
            >
              {timeline ? (
                <GameTimeline clips={group.clips} lead={lead} renderClip={renderClipCard} gameMode={group.gameMode} />
              ) : (
                <>
                  {lead}
                  {group.clips.map(renderClipCard)}
                </>
              )}
            </GameSection>
    )
  }


  const listEmpty = source === 'steam' ? clips.length === 0 && records.length === 0 : vodGroups.length === 0
  const emptyKind = emptyStateKind({
    source,
    loading: loading || !vodsLoaded,
    error: error !== null,
    empty: listEmpty,
    filtered: filterActive(appliedFilter),
    vodTotal: vods.length,
  })

  return (
    <div className="flex flex-1 flex-col">
      <FilterBar
        value={filter}
        onChange={setFilter}
        variant={source}
        viewMode={viewMode}
        onViewModeChange={(mode) => {
          setViewMode(mode)
          saveViewMode(source, mode)
        }}
        onRefresh={
          source === 'vod'
            ? () => {
                reload()
                reloadVods()
              }
            : undefined
        }
      />

      <main className="flex-1 p-4">
        {labeling && total > 0 && (
          <p className="mb-2 flex items-center gap-2 text-sm text-zinc-400">
            라벨 {labeled}/{total}
            <LabelingHelp />
          </p>
        )}
        {loading && <LoadingBar label={source === 'vod' ? '클립 목록을 불러오는 중입니다…' : '클립 목록을 불러오는 중입니다…'} />}
        {source === 'vod' && !loading && !vodsLoaded && <LoadingBar label="영상 파일 목록을 불러오는 중입니다…" />}
        {source === 'vod' && vodsLoaded && probe.active && (
          <div className="mb-3 rounded border border-zinc-700 bg-zinc-800/60 p-3">
            <LoadingBar
              label={`영상 정보를 읽는 중입니다 (${probe.done}/${probe.total})`}
              detail="용량이 큰 영상은 길이를 읽는 데 1분 넘게 걸릴 수 있습니다. 그동안에도 다른 화면은 쓸 수 있고, 끝나면 목록이 자동으로 채워집니다."
              percent={probe.percent}
            />
          </div>
        )}
        {error && <p className="text-rose-400">오류가 발생했습니다: {error}</p>}
        {actionError && <p className="mb-2 text-rose-400">{actionError}</p>}
        {reprocessKey !== null && (
          <p className="mb-2 text-sky-300">게임을 다시 분석하는 중입니다. 몇 분 걸릴 수 있으며, 끝나면 목록이 자동으로 갱신됩니다.</p>
        )}
        {notice && <p className="mb-2 text-emerald-400">{notice}</p>}
        {emptyKind !== 'none' && (
          <div className="flex min-h-[50vh] flex-col items-center justify-center gap-3 text-center text-zinc-400">
            <p className="text-base text-zinc-300">{EMPTY_TITLES[emptyKind]}</p>
            {EMPTY_HINTS[emptyKind] && <p className="max-w-md text-sm text-zinc-500">{EMPTY_HINTS[emptyKind]}</p>}
            {emptyKind === 'steam' && (
              <button
                type="button"
                className="rounded border border-sky-500/60 px-4 py-1.5 text-sm text-sky-300 hover:bg-sky-500/20"
                onClick={onBackfill}
              >
                {backfillLabel}
              </button>
            )}
            {emptyKind === 'vod-no-sources' && (
              <>
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
              </>
            )}
          </div>
        )}

        {groups.length > 0 && (
          <div className="mb-3 flex items-center gap-3 text-sm text-zinc-400">
            <span>게임 {groups.length}개</span>
            <button
              type="button"
              className="rounded border border-zinc-600 px-2 py-0.5 hover:bg-zinc-700"
              onClick={() => setExpandedKeys(new Set(groups.map((g) => g.key)))}
            >
              모두 펼치기
            </button>
            <button
              type="button"
              className="rounded border border-zinc-600 px-2 py-0.5 hover:bg-zinc-700"
              onClick={() => setExpandedKeys(new Set())}
            >
              모두 접기
            </button>
            {source === 'vod' && <VideoFormatHelp />}
          </div>
        )}
        {source === 'vod' && (
          <div className="mb-3 flex flex-wrap items-center gap-3 text-sm text-zinc-400">
            {vodDays.length > 0 && (
              <>
                <button
                  type="button"
                  className="rounded border border-zinc-600 px-2 py-0.5 hover:bg-zinc-700 disabled:opacity-40"
                  disabled={dayFold.collapsed.size === 0}
                  onClick={dayFold.expandAll}
                >
                  날짜 모두 펼치기
                </button>
                <button
                  type="button"
                  className="rounded border border-zinc-600 px-2 py-0.5 hover:bg-zinc-700 disabled:opacity-40"
                  disabled={dayFold.allCollapsed}
                  onClick={dayFold.collapseAll}
                >
                  날짜 모두 접기
                </button>
              </>
            )}
            <DayShortcutBar shortcuts={shortcutDays(vodDays, 'vod')} onGo={dayFold.go} />
          </div>
        )}

        <div className="flex flex-col gap-3">
          {source === 'steam' &&
            groupByDay(groups).map((dayGroup) => (
              <section key={dayGroup.day ?? 'unknown'} className="flex flex-col gap-3 [&+&]:mt-5">
                <GameDayHeader
                  day={dayGroup.day}
                  gameCount={dayGroup.games.length}
                  clipCount={dayGroup.games.reduce((n, g) => n + g.clips.length, 0)}
                  clipBytes={dayGroup.games.reduce((n, g) => n + totalSize(g.clips), 0)}
                />
                {dayGroup.games.map((group) => renderGame(group))}
              </section>
            ))}
          {source === 'vod' &&
            vodDateGroups.map((dateGroup) => (
              <section
                key={dateGroup.day ?? 'unknown'}
                id={dayAnchorId('vod', dateGroup.day)}
                className="flex flex-col gap-3 [&+&]:mt-5"
              >
                <GameDayHeader
                  day={dateGroup.day}
                  videoCount={dateGroup.vods.length}
                  gameCount={dateGroup.vods.reduce((n, vg) => n + (vg.vod?.games.length ?? vg.games.length), 0)}
                  clipCount={dateGroup.vods.reduce(
                    (n, vg) => n + (vg.vod?.clipCount ?? vg.games.reduce((m, g) => m + g.clips.length, 0)),
                    0,
                  )}
                  clipBytes={dateGroup.vods.reduce(
                    (n, vg) => n + (vg.vod?.clipBytes ?? vg.games.reduce((m, g) => m + totalSize(g.clips), 0)),
                    0,
                  )}
                  collapsed={dayFold.collapsed.has(dayId(dateGroup.day))}
                  onToggle={() => dayFold.toggle(dateGroup.day)}
                />
                {!dayFold.collapsed.has(dayId(dateGroup.day)) && dateGroup.vods.map((vg) => {
              const visible = vg.games.reduce((n, g) => n + g.clips.length, 0)
              const visibleBytes = vg.games.reduce((n, g) => n + totalSize(g.clips), 0)
              return (
                <VodSection
                  key={vg.vodId}
                  name={vg.name}
                  vod={vg.vod}
                  job={job?.id === vg.vodId ? job : null}
                  expanded={!collapsedVods.has(vg.vodId)}
                  gameCount={vg.vod?.games.length ?? vg.games.length}
                  clipCount={vg.vod?.clipCount ?? visible}
                  visibleGameCount={vg.games.length}
                  clipBytes={vg.vod?.clipBytes ?? visibleBytes}
                  analysisBusy={runningVodId !== null}
                  onToggle={() =>
                    setCollapsedVods((prev) => {
                      const next = new Set(prev)
                      if (!next.delete(vg.vodId)) next.add(vg.vodId)
                      return next
                    })
                  }
                  onAnalyze={(options) => vg.vod && handleAnalyze(vg.vod, options)}
                  onCancel={() => vg.vod && handleCancelAnalysis(vg.vod)}
                  onRenameStreamer={(name) => vg.vod && handleRenameStreamer(vg.vod, name)}
                  onEditDate={(date) => vg.vod && handleEditVideoDate(vg.vod, date)}
                  onDeleteClips={() => handleDeleteVod(vg.vodId, vg.name, vg.vod?.clipCount ?? visible)}
                  onDeleteVod={() => handleRemoveVod(vg.vodId, vg.name)}
                >
                  {vg.games.map((group) => renderGame(group))}
                </VodSection>
              )
                })}
              </section>
            ))}
        </div>
      </main>

      {playingIndex >= 0 && (
        <PlayerModal
          clips={ordered}
          index={playingIndex}
          onIndexChange={(i) => setPlayingId(ordered[i]?.id ?? null)}
          onLabel={handleLabel}
          onNote={handleNote}
          onExport={setExportTarget}
          onRename={handleRename}
          onTrim={async (clip, ranges) => {
            if (ranges.length === 1) {
              await trimClip(clip.id, ranges[0].start, ranges[0].end)
            } else {
              const pieces = await splitClip(clip.id, ranges)
              setPlayingId(pieces[0]?.id ?? null)
            }
            reload()
          }}
          paused={exportTarget !== null}
          onDelete={(clip) => {
            const next = ordered[playingIndex + 1] ?? ordered[playingIndex - 1]
            requestDelete(`"${clip.title}" 클립을 삭제합니다.`, async (mode) => {
              setPlayingId(next?.id ?? null)
              await deleteClip(clip.id)
              return mode
            })
          }}
          onClose={() => setPlayingId(null)}
        />
      )}
      {exportTarget && <ExportDialog clip={exportTarget} onClose={() => setExportTarget(null)} />}
      {resultViewIndex >= 0 && (
        <ResultViewer
          games={resultGames}
          index={resultViewIndex}
          onIndexChange={(i) => setResultViewKey(resultGames[i].key)}
          onClose={() => setResultViewKey(null)}
        />
      )}
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
