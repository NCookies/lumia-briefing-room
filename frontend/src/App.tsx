import { useCallback, useEffect, useMemo, useState } from 'react'
import { deleteClipForever, listClips, patchClip, restoreClip, trashClip, trimClip } from './api'
import { useConfirm } from './confirmContext'
import { getConfirmDelete, setConfirmDelete } from './exportApi'
import { ClipCard } from './components/ClipCard'
import { DEFAULT_FILTER, FilterBar, type FilterState } from './components/FilterBar'
import { ExportDialog } from './components/ExportDialog'
import { GameSection } from './components/GameSection'
import { PlayerModal } from './components/PlayerModal'
import { ResultCard, ResultViewer } from './components/ResultCard'
import { groupByGame, totalSize, type GameGroup } from './grouping'
import { applyLabel, progress } from './labeling'
import { SettingsModal } from './components/SettingsModal'
import { formatBytes } from './retention'
import type { Clip, UserLabel } from './types'

export default function App() {
  const [filter, setFilter] = useState<FilterState>(DEFAULT_FILTER)
  const [clips, setClips] = useState<Clip[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [exportTarget, setExportTarget] = useState<Clip | null>(null)
  const [showSettings, setShowSettings] = useState(false)
  const [resultViewId, setResultViewId] = useState<string | null>(null)
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set())
  const [playingId, setPlayingId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [confirmDelete, setConfirmDeleteState] = useState(true)
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
    })
      .then(setClips)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [filter])

  useEffect(() => {
    reload()
  }, [reload])

  useEffect(() => {
    getConfirmDelete()
      .then(setConfirmDeleteState)
      .catch(() => {})
  }, [])

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

  const changeConfirmDelete = (value: boolean) => {
    setConfirmDeleteState(value)
    setConfirmDelete(value).catch((e: Error) => setActionError(e.message))
  }

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
  const playingIndex = playingId === null ? -1 : ordered.findIndex((c) => c.id === playingId)
  const toggleGame = (key: string) =>
    setExpandedKeys((prev) => {
      const next = new Set(prev)
      if (!next.delete(key)) next.add(key)
      return next
    })

  const { labeled, total } = progress(ordered)

  return (
    <div className="flex min-h-screen flex-col bg-zinc-900 text-zinc-100">
      <header className="flex items-baseline justify-between border-b border-zinc-700 px-4 py-3">
        <h1 className="text-xl font-semibold">루미아 브리핑룸</h1>
        <div className="flex items-baseline gap-4">
          {!filter.trashed && total > 0 && (
            <span className="text-sm text-zinc-400">
              라벨 {labeled}/{total}
            </span>
          )}
          <button
            type="button"
            className="rounded border border-zinc-600 px-2 py-1 text-sm text-zinc-300 hover:bg-zinc-700"
            onClick={() => setShowSettings(true)}
          >
            ⚙ 옵션
          </button>
        </div>
      </header>

      <FilterBar value={filter} onChange={setFilter} />

      <main className="flex-1 p-4">
        {loading && <p className="text-zinc-400">불러오는 중입니다...</p>}
        {error && <p className="text-rose-400">오류가 발생했습니다: {error}</p>}
        {actionError && <p className="mb-2 text-rose-400">{actionError}</p>}
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
            >
              {group.result?.imagePath && (
                <ResultCard
                  clipId={group.clips[0].id}
                  result={group.result}
                  onOpen={() => setResultViewId(group.clips[0].id)}
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
      {resultViewId && <ResultViewer clipId={resultViewId} onClose={() => setResultViewId(null)} />}
      {showSettings && (
        <SettingsModal
          confirmDelete={confirmDelete}
          onConfirmDeleteChange={changeConfirmDelete}
          onClose={() => setShowSettings(false)}
        />
      )}
    </div>
  )
}
