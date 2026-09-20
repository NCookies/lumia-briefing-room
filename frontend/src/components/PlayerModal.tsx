import { useEffect } from 'react'
import { videoUrl } from '../api'
import { SIGNAL_LABELS } from '../labels'
import { applyLabel, labelForKey, nextUnlabeledIndex, progress } from '../labeling'
import type { Clip, UserLabel } from '../types'
import { LabelButtons } from './LabelButtons'
import { ScoreChip } from './ScoreChip'
import { TagBadge } from './TagBadge'

interface Props {
  clips: Clip[]
  index: number
  onIndexChange: (index: number) => void
  onLabel: (clip: Clip, label: UserLabel) => void
  onClose: () => void
}

export function PlayerModal({ clips, index, onIndexChange, onLabel, onClose }: Props) {
  const clip = clips[index]

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return
      if (e.key === 'Escape') return onClose()
      if (e.key === 'ArrowRight') return onIndexChange(Math.min(index + 1, clips.length - 1))
      if (e.key === 'ArrowLeft') return onIndexChange(Math.max(index - 1, 0))

      const label = labelForKey(e.key)
      if (label === undefined) return
      onLabel(clip, label)
      if (label === null) return
      const next = nextUnlabeledIndex(applyLabel(clips, clip.id, label), index)
      if (next !== null) onIndexChange(next)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [clips, clip, index, onClose, onIndexChange, onLabel])

  const { labeled, total } = progress(clips)

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-2"
      onClick={onClose}
    >
      <div
        className="flex w-[min(97vw,calc((100vh-8.5rem)*1.7778))] flex-col gap-2"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex flex-wrap items-center justify-between gap-2 text-zinc-100">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-medium">{clip.title}</h2>
            <ScoreChip score={clip.pvpScore} signals={clip.pvpSignals ?? []} />
            {clip.audioStatus && clip.audioStatus !== 'full' && (
              <span className="rounded border border-amber-500/50 px-1.5 py-0.5 text-xs text-amber-300">
                {clip.audioStatus === 'none' ? '소리 없음 (원본에 오디오가 없다)' : '소리 일부 (원본 오디오 일부 소실)'}
              </span>
            )}
            {clip.labelConflict && (
              <span className="rounded border border-sky-500/50 px-1.5 py-0.5 text-xs text-sky-300">
                이관된 라벨 · 확인 필요
              </span>
            )}
            {clip.region && (
              <span className="rounded border border-zinc-600 px-1.5 py-0.5 text-xs text-zinc-300">
                {clip.region}
              </span>
            )}
            {clip.tags.map((t) => (
              <TagBadge key={t} tag={t} />
            ))}
          </div>
          <button
            type="button"
            className="rounded px-2 py-1 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-100"
            onClick={onClose}
          >
            닫기 ✕
          </button>
        </div>

        <video
          key={clip.id}
          src={videoUrl(clip.id)}
          controls
          autoPlay
          className="aspect-video w-full rounded bg-black object-contain"
        />

        <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-zinc-300">
          <div className="flex items-center gap-4">
            <LabelButtons
              value={clip.userLabel}
              onChange={(l) => {
                onLabel(clip, l)
                if (l === null) return
                const next = nextUnlabeledIndex(applyLabel(clips, clip.id, l), index)
                if (next !== null) onIndexChange(next)
              }}
              showKeys
              size="lg"
            />
            <span className="text-xs text-zinc-500">
              근거:{' '}
              {(clip.pvpSignals ?? []).length
                ? clip.pvpSignals.map((s) => SIGNAL_LABELS[s] ?? s).join(' · ')
                : '없음'}
            </span>
          </div>
          <div className="flex items-center gap-4 text-xs text-zinc-400">
            <span>
              라벨 {labeled}/{total} · {index + 1}번째
            </span>
            <span>
              <kbd className="rounded bg-zinc-700 px-1">←</kbd>
              <kbd className="ml-1 rounded bg-zinc-700 px-1">→</kbd> 이동 ·{' '}
              <kbd className="rounded bg-zinc-700 px-1">0</kbd> 라벨 해제 ·{' '}
              <kbd className="rounded bg-zinc-700 px-1">Esc</kbd> 닫기
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
