import { useState } from 'react'
import { thumbnailUrl } from '../api'
import type { Clip } from '../types'
import { TagBadge } from './TagBadge'

interface Props {
  clip: Clip
  trashed: boolean
  onPlay: (clip: Clip) => void
  onTogglePin: (clip: Clip) => void
  onRename: (clip: Clip, title: string) => void
  onTrash: (clip: Clip) => void
  onRestore: (clip: Clip) => void
  onDeleteForever: (clip: Clip) => void
}

function formatDuration(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

export function ClipCard({
  clip,
  trashed,
  onPlay,
  onTogglePin,
  onRename,
  onTrash,
  onRestore,
  onDeleteForever,
}: Props) {
  const [editing, setEditing] = useState(false)
  const [draftTitle, setDraftTitle] = useState(clip.title)

  const commitRename = () => {
    setEditing(false)
    if (draftTitle.trim() && draftTitle !== clip.title) {
      onRename(clip, draftTitle.trim())
    } else {
      setDraftTitle(clip.title)
    }
  }

  return (
    <div className="flex flex-col overflow-hidden rounded-lg border border-zinc-700 bg-zinc-800/60">
      <button
        type="button"
        className="group relative aspect-video w-full overflow-hidden bg-zinc-900"
        onClick={() => onPlay(clip)}
      >
        {clip.thumbnailPath ? (
          <img
            src={thumbnailUrl(clip.id)}
            alt={clip.title}
            className="h-full w-full object-cover transition-transform group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-zinc-500">
            썸네일 없음
          </div>
        )}
        <span className="absolute bottom-1 right-1 rounded bg-black/70 px-1 text-xs">
          {formatDuration(clip.durationSec)}
        </span>
        {clip.sourceIncomplete && (
          <span className="absolute left-1 top-1 rounded bg-amber-600/90 px-1 text-xs">
            일부 손실
          </span>
        )}
      </button>

      <div className="flex flex-1 flex-col gap-2 p-2">
        {editing ? (
          <input
            className="rounded border border-zinc-600 bg-zinc-900 px-1 py-0.5 text-sm text-zinc-100"
            value={draftTitle}
            autoFocus
            onChange={(e) => setDraftTitle(e.target.value)}
            onBlur={commitRename}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitRename()
              if (e.key === 'Escape') {
                setDraftTitle(clip.title)
                setEditing(false)
              }
            }}
          />
        ) : (
          <button
            type="button"
            className="truncate text-left text-sm font-medium text-zinc-100 hover:underline"
            title="더블클릭해서 제목 수정"
            onDoubleClick={() => setEditing(true)}
          >
            {clip.title}
          </button>
        )}

        <div className="flex flex-wrap gap-1">
          {clip.tags.map((t) => (
            <TagBadge key={t} tag={t} />
          ))}
        </div>

        <div className="mt-auto flex items-center justify-between pt-1">
          {trashed ? (
            <div className="flex gap-2 text-xs">
              <button
                type="button"
                className="text-sky-400 hover:underline"
                onClick={() => onRestore(clip)}
              >
                복구
              </button>
              <button
                type="button"
                className="text-rose-400 hover:underline"
                onClick={() => onDeleteForever(clip)}
              >
                완전 삭제
              </button>
            </div>
          ) : (
            <div className="flex gap-2 text-xs">
              <button
                type="button"
                className={clip.pinned ? 'text-amber-400' : 'text-zinc-400 hover:text-amber-300'}
                onClick={() => onTogglePin(clip)}
              >
                {clip.pinned ? '고정됨' : '고정'}
              </button>
              <button
                type="button"
                className="text-zinc-400 hover:text-rose-400"
                onClick={() => onTrash(clip)}
              >
                삭제
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
