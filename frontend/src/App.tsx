import { useCallback, useEffect, useMemo, useState } from 'react'
import { deleteClipForever, listClips, patchClip, restoreClip, trashClip } from './api'
import { ClipCard } from './components/ClipCard'
import { DEFAULT_FILTER, FilterBar, type FilterState } from './components/FilterBar'
import { PlayerModal } from './components/PlayerModal'
import { groupByGame } from './grouping'
import { applyLabel, progress } from './labeling'
import type { Clip, UserLabel } from './types'

const GAME_COLORS = [
  { border: 'border-sky-500/70', header: 'bg-sky-500/25 text-sky-100' },
  { border: 'border-emerald-500/70', header: 'bg-emerald-500/25 text-emerald-100' },
  { border: 'border-amber-500/70', header: 'bg-amber-500/25 text-amber-100' },
  { border: 'border-fuchsia-500/70', header: 'bg-fuchsia-500/25 text-fuchsia-100' },
  { border: 'border-rose-500/70', header: 'bg-rose-500/25 text-rose-100' },
]

function formatGameStart(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('ko-KR', { hour12: false })
}

export default function App() {
  const [filter, setFilter] = useState<FilterState>(DEFAULT_FILTER)
  const [clips, setClips] = useState<Clip[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [playingId, setPlayingId] = useState<string | null>(null)

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

  const groups = useMemo(() => groupByGame(clips, filter.sort), [clips, filter.sort])
  const ordered = useMemo(() => groups.flatMap((g) => g.clips), [groups])
  const playingIndex = playingId === null ? -1 : ordered.findIndex((c) => c.id === playingId)
  const { labeled, total } = progress(ordered)

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

        <div className="flex flex-col gap-6">
          {groups.map((group) => (
            <section
              key={group.key}
              className={`overflow-hidden rounded-xl border-2 ${GAME_COLORS[(group.number - 1) % GAME_COLORS.length].border}`}
            >
              <h2
                className={`flex items-baseline gap-3 px-4 py-2 text-base font-semibold ${GAME_COLORS[(group.number - 1) % GAME_COLORS.length].header}`}
              >
                <span>게임 {group.number}</span>
                <span className="text-xs font-normal opacity-80">
                  {formatGameStart(group.matchStartUtc)} · 클립 {group.clips.length}개
                </span>
              </h2>
              <div className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
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
                  />
                ))}
              </div>
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
          onTrash={(clip) => {
            const next = ordered[playingIndex + 1] ?? ordered[playingIndex - 1]
            setPlayingId(next?.id ?? null)
            void handleTrash(clip)
          }}
          onClose={() => setPlayingId(null)}
        />
      )}
    </div>
  )
}
