import { useEffect, useRef, useState } from 'react'
import { ClipId } from './ClipId'
import { ClipVideo } from './ClipVideo'
import { SIGNAL_LABELS } from '../labels'
import { applyLabel, labelForKey, nextUnlabeledIndex, progress } from '../labeling'
import type { Clip, UserLabel } from '../types'
import { loadVolume, saveVolume } from '../volume'
import { useLabelingUi } from '../labelingContext'
import { LabelButtons } from './LabelButtons'
import { LabelNoteInput } from './LabelNoteInput'
import { ScoreChip } from './ScoreChip'
import { TagBadge } from './TagBadge'
import type { TrimRange } from '../trimming'
import { TrimPanel } from './TrimPanel'

interface Props {
  clips: Clip[]
  index: number
  onIndexChange: (index: number) => void
  onLabel: (clip: Clip, label: UserLabel) => void
  onNote: (clip: Clip, note: string | null) => void
  onTrash: (clip: Clip) => void
  onRename: (clip: Clip, title: string) => void
  onExport: (clip: Clip) => void
  onTrim: (clip: Clip, ranges: TrimRange[]) => Promise<void>
  paused: boolean
  onClose: () => void
}

export function PlayerModal({
  clips,
  index,
  onIndexChange,
  onLabel,
  onNote,
  onTrash,
  onRename,
  onExport,
  onTrim,
  paused,
  onClose,
}: Props) {
  const clip = clips[index]
  const labeling = useLabelingUi()
  const volumeRef = useRef(loadVolume())
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const [trimming, setTrimming] = useState(false)
  const [trimBusy, setTrimBusy] = useState(false)
  const [editingTitle, setEditingTitle] = useState(false)
  const [draftTitle, setDraftTitle] = useState('')
  const editingRef = useRef(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (paused) return
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (trimming) {
        if (e.key === 'Escape') setTrimming(false)
        return
      }
      if (e.key === 'Escape') return onClose()
      if (e.key === 'ArrowRight') return onIndexChange(Math.min(index + 1, clips.length - 1))
      if (e.key === 'ArrowLeft') return onIndexChange(Math.max(index - 1, 0))

      if (!labeling) return
      const label = labelForKey(e.key)
      if (label === undefined) return
      onLabel(clip, label)
      if (label === null) return
      const next = nextUnlabeledIndex(applyLabel(clips, clip.id, label), index)
      if (next !== null) onIndexChange(next)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [clips, clip, index, paused, trimming, labeling, onClose, onIndexChange, onLabel])

  const startRename = () => {
    setDraftTitle(clip.title)
    editingRef.current = true
    setEditingTitle(true)
  }

  const cancelRename = () => {
    editingRef.current = false
    setEditingTitle(false)
  }

  const commitRename = () => {
    if (!editingRef.current) return
    editingRef.current = false
    setEditingTitle(false)
    const title = draftTitle.trim()
    if (title && title !== clip.title) onRename(clip, title)
  }

  const { labeled, total } = progress(clips)
  const hasPrev = index > 0
  const hasNext = index < clips.length - 1
  const NAV =
    'fixed top-1/2 z-[60] flex h-24 w-14 -translate-y-1/2 items-center justify-center rounded-xl bg-zinc-800/80 text-4xl text-zinc-100 hover:bg-zinc-600 disabled:cursor-default disabled:opacity-20 disabled:hover:bg-zinc-800/80'

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-2"
      onClick={onClose}
    >
      <button
        type="button"
        aria-label="이전 영상"
        className={`${NAV} left-2`}
        disabled={!hasPrev}
        onClick={(e) => {
          e.stopPropagation()
          onIndexChange(index - 1)
        }}
      >
        ‹
      </button>
      <button
        type="button"
        aria-label="다음 영상"
        className={`${NAV} right-2`}
        disabled={!hasNext}
        onClick={(e) => {
          e.stopPropagation()
          onIndexChange(index + 1)
        }}
      >
        ›
      </button>
      <div
        className={`flex flex-col gap-2 ${
          trimming
            ? 'w-[min(97vw,calc((100vh-16.5rem)*1.7778))]'
            : 'w-[min(97vw,calc((100vh-8.5rem)*1.7778))]'
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex flex-wrap items-center justify-between gap-2 text-zinc-100">
          <div className="flex flex-wrap items-center gap-2">
            {editingTitle ? (
              <input
                className="w-[28rem] max-w-full rounded border border-zinc-600 bg-zinc-900 px-2 py-0.5 text-lg text-zinc-100"
                value={draftTitle}
                autoFocus
                onChange={(e) => setDraftTitle(e.target.value)}
                onBlur={commitRename}
                onKeyDown={(e) => {
                  e.stopPropagation()
                  if (e.key === 'Enter') commitRename()
                  if (e.key === 'Escape') cancelRename()
                }}
              />
            ) : (
              <>
                <h2 className="text-lg font-medium">{clip.title}</h2>
                <ClipId id={clip.id} />
                <button
                  type="button"
                  aria-label="이름 수정"
                  title="이름 수정"
                  className="rounded px-1.5 py-0.5 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-100"
                  onClick={startRename}
                >
                  ✎
                </button>
              </>
            )}
            <ScoreChip score={clip.pvpScore} signals={clip.pvpSignals ?? []} />
            {clip.audioStatus && clip.audioStatus !== 'full' && (
              <span className="rounded border border-amber-500/50 px-1.5 py-0.5 text-xs text-amber-300">
                {clip.audioStatus === 'none' ? '소리 없음 (원본에 오디오가 없습니다)' : '소리 일부 (원본 오디오가 일부 유실되었습니다)'}
              </span>
            )}
            {clip.labelConflict && (
              <span className="rounded border border-sky-500/50 px-1.5 py-0.5 text-xs text-sky-300">
                옮겨 온 라벨 · 확인 필요
              </span>
            )}
            {clip.region && (
              <span className="rounded border border-zinc-600 px-1.5 py-0.5 text-xs text-zinc-300">
                {clip.region}
              </span>
            )}
            {clip.trimmed && (
              <span className="rounded border border-amber-500/50 px-1.5 py-0.5 text-xs text-amber-300">편집됨</span>
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

        <ClipVideo
          key={`${clip.id}-${clip.durationSec}`}
          clipId={clip.id}
          version={clip.durationSec}
          videoRef={(el) => {
            videoRef.current = el
            if (!el) return
            el.volume = volumeRef.current.volume
            el.muted = volumeRef.current.muted
          }}
          onVolumeChange={(v) => {
            volumeRef.current = { volume: v.volume, muted: v.muted }
            saveVolume(volumeRef.current)
          }}
        />

        {trimming && (
          <TrimPanel
            key={`${clip.id}-${clip.durationSec}`}
            duration={clip.durationSec}
            getVideo={() => videoRef.current}
            busy={trimBusy}
            onCancel={() => setTrimming(false)}
            onApply={async (ranges) => {
              setTrimBusy(true)
              try {
                await onTrim(clip, ranges)
                setTrimming(false)
              } catch (e) {
                alert((e as Error).message)
              } finally {
                setTrimBusy(false)
              }
            }}
          />
        )}

        {labeling && clip.userLabel !== null && (
          <LabelNoteInput clipId={clip.id} value={clip.labelNote} onSave={(note) => onNote(clip, note)} />
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-zinc-300">
          <div className="flex items-center gap-4">
            {labeling && (
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
            )}
            <span className="text-xs text-zinc-500">
              근거:{' '}
              {(clip.pvpSignals ?? []).length
                ? clip.pvpSignals.map((s) => SIGNAL_LABELS[s] ?? s).join(' · ')
                : '없음'}
            </span>
          </div>
          <div className="flex items-center gap-4 text-xs text-zinc-400">
            <button
              type="button"
              className={`rounded border px-3 py-1 text-sm ${
                trimming
                  ? 'border-amber-400 bg-amber-400/20 text-amber-200'
                  : 'border-amber-500/50 text-amber-300 hover:bg-amber-500/20'
              }`}
              onClick={() => setTrimming((t) => !t)}
            >
              ✂ 자르기
            </button>
            <button
              type="button"
              className="rounded border border-sky-500/50 px-3 py-1 text-sm text-sky-300 hover:bg-sky-500/20"
              onClick={() => onExport(clip)}
            >
              저장
            </button>
            <button
              type="button"
              className="rounded border border-rose-500/50 px-3 py-1 text-sm text-rose-300 hover:bg-rose-500/20"
              onClick={() => onTrash(clip)}
            >
              삭제
            </button>
            <span>
              {labeling && `라벨 ${labeled}/${total} · `}
              {index + 1}번째
            </span>
            <span>
              <kbd className="rounded bg-zinc-700 px-1">←</kbd>
              <kbd className="ml-1 rounded bg-zinc-700 px-1">→</kbd> 이동 ·{' '}
              {labeling && (
                <>
                  <kbd className="rounded bg-zinc-700 px-1">0</kbd> 라벨 해제 ·{' '}
                </>
              )}
              <kbd className="rounded bg-zinc-700 px-1">Esc</kbd> 닫기
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
