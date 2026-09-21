import { useEffect, useState } from 'react'
import { clampRange, formatTime, MIN_LENGTH, type TrimRange } from '../trimming'

interface Props {
  duration: number
  getVideo: () => HTMLVideoElement | null
  busy: boolean
  onApply: (start: number, end: number) => void
  onCancel: () => void
}

export function TrimPanel({ duration, getVideo, busy, onApply, onCancel }: Props) {
  const [range, setRange] = useState<TrimRange>({ start: 0, end: duration })
  const [previewing, setPreviewing] = useState(false)

  useEffect(() => {
    if (!previewing) return
    const video = getVideo()
    if (!video) return
    const onTime = () => {
      if (video.currentTime >= range.end) {
        video.pause()
        setPreviewing(false)
      }
    }
    video.addEventListener('timeupdate', onTime)
    return () => video.removeEventListener('timeupdate', onTime)
  }, [previewing, range.end, getVideo])

  const move = (handle: 'start' | 'end', value: number) => {
    const next = clampRange(range, handle, value, duration)
    setRange(next)
    setPreviewing(false)
    const video = getVideo()
    if (video) {
      video.pause()
      video.currentTime = handle === 'start' ? next.start : next.end
    }
  }

  const fromPlayhead = (handle: 'start' | 'end') => {
    const video = getVideo()
    if (video) setRange(clampRange(range, handle, video.currentTime, duration))
  }

  const preview = () => {
    const video = getVideo()
    if (!video) return
    video.currentTime = range.start
    setPreviewing(true)
    void video.play()
  }

  const kept = range.end - range.start
  const removed = duration - kept
  const pct = (t: number) => `${(t / duration) * 100}%`

  const apply = () => {
    if (!confirm(`${formatTime(range.start)} ~ ${formatTime(range.end)} 구간만 남기고 나머지 ${removed.toFixed(1)}초는 삭제합니다. 삭제한 부분은 복구할 수 없습니다. 계속하시겠습니까?`)) return
    onApply(range.start, range.end)
  }

  return (
    <div className="flex flex-col gap-2 rounded border border-sky-500/40 bg-zinc-800/80 p-3 text-sm text-zinc-200">
      <div className="relative h-8">
        <div className="absolute inset-x-0 top-1/2 h-2 -translate-y-1/2 rounded bg-zinc-700" />
        <div
          className="absolute top-1/2 h-2 -translate-y-1/2 rounded bg-sky-500/70"
          style={{ left: pct(range.start), width: pct(kept) }}
        />
        <input
          type="range"
          className="dual-range"
          aria-label="시작 위치"
          min={0}
          max={duration}
          step={0.1}
          value={range.start}
          onChange={(e) => move('start', Number(e.target.value))}
        />
        <input
          type="range"
          className="dual-range"
          aria-label="끝 위치"
          min={0}
          max={duration}
          step={0.1}
          value={range.end}
          onChange={(e) => move('end', Number(e.target.value))}
        />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <span>
          {formatTime(range.start)} ~ {formatTime(range.end)}
        </span>
        <span className="text-zinc-400">
          남는 길이 {kept.toFixed(1)}초 · 삭제 {removed.toFixed(1)}초 (최소 {MIN_LENGTH}초 이상)
        </span>
        <button type="button" className="rounded border border-zinc-600 px-2 py-1 hover:bg-zinc-700" onClick={() => fromPlayhead('start')}>
          현재 위치를 시작으로
        </button>
        <button type="button" className="rounded border border-zinc-600 px-2 py-1 hover:bg-zinc-700" onClick={() => fromPlayhead('end')}>
          현재 위치를 끝으로
        </button>
        <button type="button" className="rounded border border-zinc-600 px-2 py-1 hover:bg-zinc-700" onClick={preview}>
          ▶ 구간 미리보기
        </button>
        <div className="ml-auto flex gap-2">
          <button type="button" className="rounded px-3 py-1 text-zinc-300 hover:bg-zinc-700" onClick={onCancel}>
            취소
          </button>
          <button
            type="button"
            className="rounded bg-rose-600 px-3 py-1 hover:bg-rose-500 disabled:opacity-40"
            disabled={busy || removed < 0.05}
            onClick={apply}
          >
            {busy ? '자르는 중...' : '구간만 남기고 나머지 삭제'}
          </button>
        </div>
      </div>
    </div>
  )
}
