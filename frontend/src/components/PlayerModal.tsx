import { useEffect, useRef, useState } from 'react'
import { videoUrl } from '../api'
import { SIGNAL_LABELS } from '../labels'
import { applyLabel, labelForKey, nextUnlabeledIndex, progress } from '../labeling'
import type { Clip, UserLabel } from '../types'
import { loadVolume, saveVolume } from '../volume'
import { LabelButtons } from './LabelButtons'
import { ScoreChip } from './ScoreChip'
import { TagBadge } from './TagBadge'
import { TrimPanel } from './TrimPanel'

interface Props {
  clips: Clip[]
  index: number
  onIndexChange: (index: number) => void
  onLabel: (clip: Clip, label: UserLabel) => void
  onTrash: (clip: Clip) => void
  onExport: (clip: Clip) => void
  onTrim: (clip: Clip, start: number, end: number) => Promise<void>
  paused: boolean
  onClose: () => void
}

export function PlayerModal({
  clips,
  index,
  onIndexChange,
  onLabel,
  onTrash,
  onExport,
  onTrim,
  paused,
  onClose,
}: Props) {
  const clip = clips[index]
  const volumeRef = useRef(loadVolume())
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const [trimming, setTrimming] = useState(false)
  const [trimBusy, setTrimBusy] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (paused) return
      if (e.target instanceof HTMLInputElement) return
      if (trimming) {
        if (e.key === 'Escape') setTrimming(false)
        return
      }
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
  }, [clips, clip, index, paused, trimming, onClose, onIndexChange, onLabel])

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
        className="flex w-[min(97vw,calc((100vh-8.5rem)*1.7778))] flex-col gap-2"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex flex-wrap items-center justify-between gap-2 text-zinc-100">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-medium">{clip.title}</h2>
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

        <video
          key={`${clip.id}-${clip.durationSec}`}
          ref={(el) => {
            videoRef.current = el
            if (!el) return
            el.volume = volumeRef.current.volume
            el.muted = volumeRef.current.muted
          }}
          onVolumeChange={(e) => {
            const v = e.currentTarget
            volumeRef.current = { volume: v.volume, muted: v.muted }
            saveVolume(volumeRef.current)
          }}
          src={videoUrl(clip.id, clip.durationSec)}
          controls
          autoPlay
          className="aspect-video w-full rounded bg-black object-contain"
        />

        {trimming && (
          <TrimPanel
            key={`${clip.id}-${clip.durationSec}`}
            duration={clip.durationSec}
            getVideo={() => videoRef.current}
            busy={trimBusy}
            onCancel={() => setTrimming(false)}
            onApply={async (start, end) => {
              setTrimBusy(true)
              try {
                await onTrim(clip, start, end)
                setTrimming(false)
              } catch (e) {
                alert((e as Error).message)
              } finally {
                setTrimBusy(false)
              }
            }}
          />
        )}

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
