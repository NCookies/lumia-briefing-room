import { useCallback, useEffect, useState } from 'react'
import { deleteClipForever, listClips, patchClip, restoreClip, trashClip } from './api'
import { ClipCard } from './components/ClipCard'
import { DEFAULT_FILTER, FilterBar, type FilterState } from './components/FilterBar'
import { PlayerModal } from './components/PlayerModal'
import { applyLabel, progress } from './labeling'
import type { Clip, UserLabel } from './types'

export default function App() {
  const [filter, setFilter] = useState<FilterState>(DEFAULT_FILTER)
  const [clips, setClips] = useState<Clip[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [playingIndex, setPlayingIndex] = useState<number | null>(null)

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
      sort: filter.sort,
    })
      .then(setClips)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [filter])

  useEffect(() => {
    reload()
  }, [reload])

  const handleTogglePin = async (clip: Clip) => {
    await patchClip(clip.id, { pinned: !clip.pinned })
    reload()
  }

  const handleRename = async (clip: Clip, title: string) => {
    await patchClip(clip.id, { title })
    reload()
  }

  const handleTrash = async (clip: Clip) => {
    await trashClip(clip.id)
    reload()
  }

  const handleRestore = async (clip: Clip) => {
    await restoreClip(clip.id)
    reload()
  }

  const handleDeleteForever = async (clip: Clip) => {
    if (!confirm(`"${clip.title}" 를 되돌릴 수 없게 완전히 삭제한다. 계속할까?`)) return
    await deleteClipForever(clip.id)
    reload()
  }

  const handleLabel = (clip: Clip, label: UserLabel) => {
    setClips((prev) => applyLabel(prev, clip.id, label))
    patchClip(clip.id, { userLabel: label }).catch((e: Error) => {
      setError(`라벨 저장 실패: ${e.message}`)
      reload()
    })
  }

  const { labeled, total } = progress(clips)

  return (
    <div className="flex min-h-screen flex-col bg-zinc-900 text-zinc-100">
      <header className="flex items-baseline justify-between border-b border-zinc-700 px-4 py-3">
        <h1 className="text-xl font-semibold">루미아 브리핑룸</h1>
        {!filter.trashed && total > 0 && (
          <span className="text-sm text-zinc-400">
            라벨 {labeled}/{total}
          </span>
        )}
      </header>

      <FilterBar value={filter} onChange={setFilter} />

      <main className="flex-1 p-4">
        {loading && <p className="text-zinc-400">불러오는 중...</p>}
        {error && <p className="text-rose-400">오류: {error}</p>}
        {!loading && !error && clips.length === 0 && (
          <p className="text-zinc-500">
            {filter.trashed ? '휴지통이 비어 있다' : '조건에 맞는 클립이 없다'}
          </p>
        )}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {clips.map((clip, i) => (
            <ClipCard
              key={clip.id}
              clip={clip}
              trashed={filter.trashed}
              onPlay={() => setPlayingIndex(i)}
              onTogglePin={handleTogglePin}
              onRename={handleRename}
              onTrash={handleTrash}
              onRestore={handleRestore}
              onDeleteForever={handleDeleteForever}
              onLabel={handleLabel}
            />
          ))}
        </div>
      </main>

      {playingIndex !== null && clips[playingIndex] && (
        <PlayerModal
          clips={clips}
          index={playingIndex}
          onIndexChange={setPlayingIndex}
          onLabel={handleLabel}
          onClose={() => setPlayingIndex(null)}
        />
      )}
    </div>
  )
}
