import { useState } from 'react'
import { thumbnailUrl } from '../api'
import type { Clip, UserLabel } from '../types'
import { LabelButtons } from './LabelButtons'
import { ScoreChip } from './ScoreChip'
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
  onLabel: (clip: Clip, label: UserLabel) => void
  onExport: (clip: Clip) => void
}

function formatDuration(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

const BORDER: Record<string, string> = {
  pvp: 'border-emerald-500/60',
  pve: 'border-zinc-600 opacity-70',
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
  onLabel,
  onExport,
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
    <div
      className={`flex flex-col overflow-hidden rounded-lg border bg-zinc-800/60 ${
        (clip.userLabel && BORDER[clip.userLabel]) || 'border-zinc-700'
      }`}
    >
      <button
        type="button"
        className="group relative aspect-video w-full overflow-hidden bg-zinc-900"
        onClick={() => onPlay(clip)}
      >
        {clip.thumbnailPath ? (
          <img
            src={thumbnailUrl(clip.id, clip.durationSec)}
            alt={clip.title}
            className="h-full w-full object-cover transition-transform group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-zinc-500">썸네일 없음</div>
        )}
        <span className="absolute bottom-1 right-1 rounded bg-black/70 px-1 text-xs">
          {formatDuration(clip.durationSec)}
        </span>
        <span className="absolute left-1 top-1">
          <ScoreChip score={clip.pvpScore} signals={clip.pvpSignals ?? []} />
        </span>
        {clip.labelConflict && (
          <span
            className="absolute bottom-6 left-1 rounded bg-sky-600/90 px-1 text-xs"
            title="이전 버전에서 교전/사냥 라벨이 섞여 있어 자동으로 옮겨 온 라벨입니다. 맞다면 같은 버튼을 한 번 더 눌러 확정하세요."
          >
            옮겨 온 라벨 · 확인 필요
          </span>
        )}
        {clip.audioStatus && clip.audioStatus !== 'full' && (
          <span className="absolute bottom-1 left-1 rounded bg-black/70 px-1 text-xs text-amber-300">
            {clip.audioStatus === 'none' ? '소리 없음' : '소리 일부'}
          </span>
        )}
        {clip.sourceIncomplete && (
          <span className="absolute right-1 top-1 rounded bg-amber-600/90 px-1 text-xs">일부 손실</span>
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
            title="더블클릭하여 제목을 수정할 수 있습니다"
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
            <>
              <LabelButtons value={clip.userLabel} onChange={(l) => onLabel(clip, l)} onlyActive />
              <div className="flex gap-2 text-xs">
                <button
                  type="button"
                  className="text-zinc-400 hover:text-sky-300"
                  onClick={() => onExport(clip)}
                >
                  저장
                </button>
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
            </>
          )}
        </div>
      </div>
    </div>
  )
}
