import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  deleteClipForever,
  emptyTrash,
  getReprocessStatus,
  listClips,
  patchClip,
  restoreClip,
  startReprocess,
  trashClip,
  trimClip,
} from '../api'
import { useConfirm } from '../confirmContext'
import { ClipCard } from './ClipCard'
import { DEFAULT_FILTER, FilterBar, type FilterState } from './FilterBar'
import { ExportDialog } from './ExportDialog'
import { GameSection } from './GameSection'
import { PlayerModal } from './PlayerModal'
import { ResultCard, ResultViewer } from './ResultCard'
import { formatMatchResult, groupByGame, totalSize, withResultImage, type GameGroup } from '../grouping'
import { applyLabel, progress } from '../labeling'
import { formatBytes } from '../retention'
import type { Clip, UserLabel } from '../types'

export type ClipSource = 'steam' | 'vod'

interface Props {
  source: ClipSource
  active: boolean
  confirmDelete: boolean
  onConfirmDeleteChange: (value: boolean) => void
}

export function ClipBrowser({ source, active, confirmDelete, onConfirmDeleteChange }: Props) {
  const [filter, setFilter] = useState<FilterState>(source === 'vod' ? { ...DEFAULT_FILTER, sort: 'asc' } : DEFAULT_FILTER)
  const [clips, setClips] = useState<Clip[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [exportTarget, setExportTarget] = useState<Clip | null>(null)
  const [resultViewKey, setResultViewKey] = useState<string | null>(null)
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set())
  const [playingId, setPlayingId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [reprocessKey, setReprocessKey] = useState<string | null>(null)
  const [reprocessGame, setReprocessGame] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
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
  }, [filter, source])

  useEffect(() => {
    if (active) reload()
  }, [active, reload])

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
      message: `${gameLabel(group)}의 클립을 완전히 삭제합니다. 계속하시겠습니까?`,
      confirmLabel: '완전 삭제',
      danger: true,
    })
    if (result.ok) await runAndReload(() => runAll(group.clips, deleteClipForever))
  }

  const handleLabel = (clip: Clip, label: UserLabel) => {
    setClips((prev) => applyLabel(prev, clip.id, label))
    patchClip(clip.id, { userLabel: label }).catch((e: Error) => {
      setError(`라벨을 저장하지 못했습니다: ${e.message}`)
      reload()
    })
  }

  const groups = useMemo(() => groupByGame(clips, filter.sort), [clips, filter.sort])
  const ordered = useMemo(() => groups.flatMap((g) => g.clips), [groups])
  const resultGames = useMemo(
    () =>
      withResultImage(groups).map((g) => ({
        key: g.key,
        clipId: g.clips[0].id,
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

  return (
    <div className="flex flex-1 flex-col">
      <FilterBar value={filter} onChange={setFilter} />

      <main className="flex-1 p-4">
        {!filter.trashed && total > 0 && (
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
        {!loading && !error && clips.length === 0 && (
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
          {groups.map((group) => (
            <GameSection
              key={group.key}
              group={group}
              expanded={expandedKeys.has(group.key)}
              trashed={filter.trashed}
              onToggle={() => toggleGame(group.key)}
              onTrashGame={() => handleTrashGame(group)}
              onRestoreGame={() => handleRestoreGame(group)}
              onDeleteGameForever={() => handleDeleteGameForever(group)}
              onReprocess={() => handleReprocess(group)}
              reprocessing={reprocessGame === group.key}
              reprocessBusy={reprocessKey !== null}
            >
              {group.result?.imagePath && (
                <ResultCard
                  clipId={group.clips[0].id}
                  result={group.result}
                  onOpen={() => setResultViewKey(group.key)}
                />
              )}
              {group.clips.map((clip) => (
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
              ))}
            </GameSection>
          ))}
        </div>
      </main>

      {playingIndex >= 0 && (
        <PlayerModal
          clips={ordered}
          index={playingIndex}
          onIndexChange={(i) => setPlayingId(ordered[i]?.id ?? null)}
          onLabel={handleLabel}
          onExport={setExportTarget}
          onRename={handleRename}
          onTrim={async (clip, start, end) => {
            await trimClip(clip.id, start, end)
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
