import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  deleteClipForever,
  deleteGameRecord,
  gameRecordImageUrl,
  listGameRecords,
  resultImageUrl,
  emptyTrash,
  getReprocessStatus,
  listClips,
  patchClip,
  restoreClip,
  startReprocess,
  trashClip,
  splitClip,
  trimClip,
} from '../api'
import { useConfirm } from '../confirmContext'
import { ClipCard } from './ClipCard'
import { DEFAULT_FILTER, FilterBar, type FilterState } from './FilterBar'
import { ExportDialog } from './ExportDialog'
import { GameSection } from './GameSection'
import { PlayerModal } from './PlayerModal'
import { ResultCard, ResultViewer } from './ResultCard'
import { GameTimeline } from './GameTimeline'
import { VodSection } from './VodSection'
import { loadViewMode, saveViewMode, type ViewMode } from '../viewMode'
import { formatMatchResult, gameRecordId, groupByGame, totalSize, withResultImage, type GameGroup } from '../grouping'
import { applyLabel, applyNote, progress } from '../labeling'
import { useLabelingUi } from '../labelingContext'
import { formatBytes } from '../retention'
import type { Clip, GameRecord, UserLabel } from '../types'
import {
  cancelAnalysis,
  deleteVodClipsForever,
  getAnalysis,
  listVods,
  restoreVodClips,
  setStreamer,
  startAnalysis,
  trashVodClips,
  type AnalysisJob,
} from '../vodApi'
import { formatDuration, formatGameRange, groupByVod, type Vod } from '../vodGrouping'

export type ClipSource = 'steam' | 'vod'

const filterActive = (f: FilterState): boolean =>
  f.trashed ||
  f.pinnedOnly ||
  f.tags.length > 0 ||
  f.dayNight !== '' ||
  f.gameMode !== '' ||
  f.label !== '' ||
  f.minPvpScore > 0

interface Props {
  source: ClipSource
  active: boolean
  confirmDelete: boolean
  onConfirmDeleteChange: (value: boolean) => void
}

export function ClipBrowser({ source, active, confirmDelete, onConfirmDeleteChange }: Props) {
  const [filter, setFilter] = useState<FilterState>(source === 'vod' ? { ...DEFAULT_FILTER, sort: 'asc' } : DEFAULT_FILTER)
  const labeling = useLabelingUi()
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
  const [job, setJob] = useState<AnalysisJob | null>(null)
  const [collapsedVods, setCollapsedVods] = useState<Set<string>>(new Set())
  const [playingId, setPlayingId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [reprocessKey, setReprocessKey] = useState<string | null>(null)
  const [reprocessGame, setReprocessGame] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<ViewMode>(() => loadViewMode(source))
  const ask = useConfirm()

  const reload = useCallback(() => {
    setLoading(true)
    setError(null)
    listClips({
      tags: filter.tags,
      dayNight: filter.dayNight || undefined,
      gameMode: filter.gameMode || undefined,
      pinned: filter.pinnedOnly || undefined,
      trashed: filter.trashed,
      minPvpScore: filter.minPvpScore || undefined,
      label: filter.label || undefined,
      source,
    })
      .then(setClips)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
    if (source === 'steam' && !filterActive(filter)) {
      listGameRecords()
        .then(setRecords)
        .catch(() => setRecords([]))
    } else {
      setRecords([])
    }
  }, [filter, source])

  useEffect(() => {
    if (active) reload()
  }, [active, reload])

  const reloadVods = useCallback(() => {
    if (source !== 'vod') return
    listVods()
      .then(setVods)
      .catch((e: Error) => setError(e.message))
  }, [source])

  useEffect(() => {
    if (active) reloadVods()
  }, [active, reloadVods])

  const runningVodId = vods.find((v) => v.status === 'analyzing')?.id ?? null

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

  const changeConfirmDelete = onConfirmDeleteChange

  const confirmTrash = async (message: string): Promise<boolean> => {
    if (!confirmDelete) return true
    const result = await ask({ message, confirmLabel: '삭제', danger: true, allowSkip: true })
    if (result.ok && result.skipNext) changeConfirmDelete(false)
    return result.ok
  }

  const confirmTrashClip = (clip: Clip) =>
    confirmTrash(`"${clip.title}" 클립을 삭제하시겠습니까?\n삭제한 클립은 휴지통에서 복구할 수 있습니다.`)

  const handleTogglePin = (clip: Clip) => runAndReload(() => patchClip(clip.id, { pinned: !clip.pinned }))

  const handleRename = (clip: Clip, title: string) => runAndReload(() => patchClip(clip.id, { title }))

  const handleTrash = async (clip: Clip) => {
    if (await confirmTrashClip(clip)) await runAndReload(() => trashClip(clip.id))
  }

  const handleRestore = (clip: Clip) => runAndReload(() => restoreClip(clip.id))

  const handleDeleteForever = async (clip: Clip) => {
    const result = await ask({
      message: `"${clip.title}" 클립을 완전히 삭제합니다. 계속하시겠습니까?`,
      confirmLabel: '완전 삭제',
      danger: true,
    })
    if (result.ok) await runAndReload(() => deleteClipForever(clip.id))
  }

  const gameLabel = (group: GameGroup<Clip>) =>
    `게임 ${group.number}(${group.clips.length}개, ${formatBytes(totalSize(group.clips))})`

  const handleTrashGame = async (group: GameGroup<Clip>) => {
    if (await confirmTrash(`${gameLabel(group)}의 클립을 모두 삭제하시겠습니까?\n삭제한 클립은 휴지통에서 복구할 수 있습니다.`)) {
      await runAndReload(() => runAll(group.clips, trashClip))
    }
  }

  const handleRestoreGame = (group: GameGroup<Clip>) => runAndReload(() => runAll(group.clips, restoreClip))

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
      message: `${gameLabel(group)}를 원본 녹화에서 다시 분석합니다.\n기존 클립은 라벨과 편집 내용을 포함해 휴지통으로 이동하고 새로 만듭니다.\n분석에는 몇 분이 걸릴 수 있습니다. 계속하시겠습니까?`,
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
      ? `"${vod.name}" 을 처음부터 다시 분석합니다.\n기존 클립은 라벨과 편집 내용을 포함해 휴지통으로 옮기고 새로 만듭니다.\n영상 길이에 따라 수십 분이 걸릴 수 있습니다. 계속하시겠습니까?`
      : options.rebuild
        ? `"${vod.name}" 의 클립을 저장된 판독으로 다시 만듭니다.\n기존 클립은 휴지통으로 옮기고 새로 만듭니다. 계속하시겠습니까?`
        : `"${vod.name}" 을 분석합니다.\n영상 길이에 따라 수십 분이 걸릴 수 있으며, 도중에 취소해도 다음에 이어서 할 수 있습니다. 계속하시겠습니까?`
    const result = await ask({
      message,
      confirmLabel: options.force ? '다시 분석' : options.rebuild ? '다시 만들기' : '분석 시작',
    })
    if (!result.ok) return
    setActionError(null)
    setNotice(null)
    try {
      await startAnalysis(vod.id, options)
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

  const vodAction = (action: () => Promise<unknown>) =>
    runAndReload(async () => {
      await action()
      reloadVods()
    })

  const handleTrashVod = async (id: string, name: string, count: number) => {
    if (
      await confirmTrash(
        `"${name}" 의 클립 ${count}개를 모두 삭제하시겠습니까?\n삭제한 클립은 휴지통에서 복구할 수 있습니다. 영상 파일은 지우지 않습니다.`,
      )
    ) {
      await vodAction(() => trashVodClips(id))
    }
  }

  const handleDeleteVodForever = async (id: string, name: string) => {
    const result = await ask({
      message: `"${name}" 의 휴지통 클립을 완전히 삭제합니다. 영상 파일은 지우지 않습니다. 계속하시겠습니까?`,
      confirmLabel: '완전 삭제',
      danger: true,
    })
    if (result.ok) await vodAction(() => deleteVodClipsForever(id))
  }

  const handleEmptyTrash = async () => {
    const result = await ask({
      message: `휴지통의 클립 ${clips.length}개(${formatBytes(totalSize(clips))})를 모두 완전히 삭제합니다. 계속하시겠습니까?`,
      confirmLabel: '휴지통 비우기',
      danger: true,
    })
    if (result.ok) await runAndReload(() => emptyTrash(source))
  }

  const handleDeleteGameForever = async (group: GameGroup<Clip>) => {
    const result = await ask({
      message: `${gameLabel(group)}의 클립을 완전히 삭제합니다.${source === 'steam' ? '\n게임 기록도 함께 삭제됩니다.' : ''} 계속하시겠습니까?`,
      confirmLabel: '완전 삭제',
      danger: true,
    })
    if (!result.ok) return
    await runAndReload(async () => {
      await runAll(group.clips, deleteClipForever)
      if (source === 'steam') {
        await deleteGameRecord(gameRecordId(group.clips[0]?.sessionDir, group.clips[0]?.matchStartUtc))
      }
    })
  }

  const handleDeleteRecord = async (group: GameGroup<Clip>) => {
    const result = await ask({
      message: `게임 ${group.number} 의 기록(순위·전적·결과표)을 삭제합니다. 되돌릴 수 없습니다. 계속하시겠습니까?`,
      confirmLabel: '기록 삭제',
      danger: true,
    })
    if (result.ok && group.recordId) await runAndReload(() => deleteGameRecord(group.recordId!))
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

  const steamGroups = useMemo(
    () => (source === 'steam' ? groupByGame(clips, filter.sort, records) : []),
    [source, clips, records, filter.sort],
  )
  const vodGroups = useMemo(
    () => (source === 'vod' ? groupByVod(clips, vods, filter.sort, !filter.trashed) : []),
    [source, clips, vods, filter.sort, filter.trashed],
  )
  const groups = useMemo(
    () => (source === 'steam' ? steamGroups : vodGroups.flatMap((v) => v.games)),
    [source, steamGroups, vodGroups],
  )
  const ordered = useMemo(() => groups.flatMap((g) => g.clips), [groups])
  const resultGames = useMemo(
    () =>
      withResultImage(groups).map((g) => ({
        key: g.key,
        imageUrl: g.recordId ? gameRecordImageUrl(g.recordId) : resultImageUrl(g.clips[0].id),
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
      trashed={filter.trashed}
      onPlay={() => setPlayingId(clip.id)}
      onTogglePin={handleTogglePin}
      onRename={handleRename}
      onTrash={handleTrash}
      onRestore={handleRestore}
      onDeleteForever={handleDeleteForever}
      onLabel={handleLabel}
      onExport={setExportTarget}
    />
  )

  const timeline = viewMode === 'timeline'

  const renderGame = (group: GameGroup<Clip>) => {
    const lead = group.result?.imagePath ? (
      <ResultCard
        imageUrl={group.recordId ? gameRecordImageUrl(group.recordId) : resultImageUrl(group.clips[0].id)}
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
              trashed={filter.trashed}
              onToggle={() => toggleGame(group.key)}
              onTrashGame={() => handleTrashGame(group)}
              onRestoreGame={() => handleRestoreGame(group)}
              onDeleteGameForever={() => handleDeleteGameForever(group)}
              onReprocess={() => handleReprocess(group)}
              onDeleteRecord={() => handleDeleteRecord(group)}
              reprocessing={reprocessGame === group.key}
              reprocessBusy={reprocessKey !== null}
              hideReprocess={source === 'vod'}
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
                <GameTimeline clips={group.clips} lead={lead} renderClip={renderClipCard} />
              ) : (
                <>
                  {lead}
                  {group.clips.map(renderClipCard)}
                </>
              )}
            </GameSection>
    )
  }


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
      />

      <main className="flex-1 p-4">
        {labeling && !filter.trashed && total > 0 && (
          <p className="mb-2 text-sm text-zinc-400">
            라벨 {labeled}/{total}
          </p>
        )}
        {loading && <p className="text-zinc-400">불러오는 중입니다...</p>}
        {error && <p className="text-rose-400">오류가 발생했습니다: {error}</p>}
        {actionError && <p className="mb-2 text-rose-400">{actionError}</p>}
        {reprocessKey !== null && (
          <p className="mb-2 text-sky-300">게임을 다시 분석하는 중입니다. 몇 분 걸릴 수 있으며, 끝나면 목록이 자동으로 갱신됩니다.</p>
        )}
        {notice && <p className="mb-2 text-emerald-400">{notice}</p>}
        {!loading && !error && clips.length === 0 && records.length === 0 && (
          <p className="text-zinc-500">
            {filter.trashed ? '휴지통이 비어 있습니다' : '조건에 맞는 클립이 없습니다'}
          </p>
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
            {filter.trashed && (
              <button
                type="button"
                className="ml-auto rounded border border-rose-500/60 px-3 py-0.5 text-rose-300 hover:bg-rose-500/20"
                onClick={handleEmptyTrash}
              >
                휴지통 비우기 ({clips.length}개 · {formatBytes(totalSize(clips))})
              </button>
            )}
          </div>
        )}

        <div className="flex flex-col gap-3">
          {source === 'steam' && groups.map((group) => renderGame(group))}
          {source === 'vod' &&
            vodGroups.map((vg) => {
              const visible = vg.games.reduce((n, g) => n + g.clips.length, 0)
              const visibleBytes = vg.games.reduce((n, g) => n + totalSize(g.clips), 0)
              const trashedView = filter.trashed
              return (
                <VodSection
                  key={vg.vodId}
                  name={vg.name}
                  vod={vg.vod}
                  job={job?.id === vg.vodId ? job : null}
                  expanded={!collapsedVods.has(vg.vodId)}
                  trashed={trashedView}
                  gameCount={trashedView ? vg.games.length : (vg.vod?.games.length ?? vg.games.length)}
                  clipCount={trashedView ? visible : (vg.vod?.clipCount ?? visible)}
                  visibleClipCount={visible}
                  clipBytes={trashedView ? visibleBytes : (vg.vod?.clipBytes ?? visibleBytes)}
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
                  onTrashClips={() => handleTrashVod(vg.vodId, vg.name, vg.vod?.clipCount ?? visible)}
                  onRestoreClips={() => vodAction(() => restoreVodClips(vg.vodId))}
                  onDeleteClipsForever={() => handleDeleteVodForever(vg.vodId, vg.name)}
                >
                  {vg.games.map((group) => renderGame(group))}
                </VodSection>
              )
            })}
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
          onTrash={async (clip) => {
            const next = ordered[playingIndex + 1] ?? ordered[playingIndex - 1]
            if (!(await confirmTrashClip(clip))) return
            setPlayingId(next?.id ?? null)
            await runAndReload(() => trashClip(clip.id))
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
    </div>
  )
}
