import { useEffect, useState } from 'react'
import { useConfirm } from '../confirmContext'
import { addRange, clampRangeAt, formatTime, initialRange, MIN_LENGTH, removeRange, splitSummary, type TrimRange } from '../trimming'

interface Props {
  duration: number
  getVideo: () => HTMLVideoElement | null
  busy: boolean
  onApply: (ranges: TrimRange[]) => void
  onCancel: () => void
}

export function TrimPanel({ duration, getVideo, busy, onApply, onCancel }: Props) {
  const ask = useConfirm()
  const [ranges, setRanges] = useState<TrimRange[]>(() => [initialRange(getVideo()?.currentTime ?? 0, duration)])
  const [active, setActive] = useState(0)
  const [previewing, setPreviewing] = useState(false)
  const range = ranges[active]

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
    const next = clampRangeAt(ranges, active, handle, value, duration)
    setRanges(next)
    setPreviewing(false)
    const video = getVideo()
    if (video) {
      video.pause()
      video.currentTime = handle === 'start' ? next[active].start : next[active].end
    }
  }

  const fromPlayhead = (handle: 'start' | 'end') => {
    const video = getVideo()
    if (video) setRanges(clampRangeAt(ranges, active, handle, video.currentTime, duration))
  }

  const preview = () => {
    const video = getVideo()
    if (!video) return
    video.currentTime = range.start
    setPreviewing(true)
    void video.play()
  }

  const add = () => {
    const added = addRange(ranges, getVideo()?.currentTime ?? 0, duration)
    if (!added) return
    setRanges(added.ranges)
    setActive(added.index)
    setPreviewing(false)
  }

  const remove = (index: number) => {
    setRanges(removeRange(ranges, index))
    setActive(Math.max(0, index <= active ? active - 1 : active))
    setPreviewing(false)
  }

  const { count, kept, removed } = splitSummary(ranges, duration)
  const canAdd = addRange(ranges, getVideo()?.currentTime ?? 0, duration) !== null
  const pct = (t: number) => `${(t / duration) * 100}%`

  const apply = async () => {
    const message =
      count === 1
        ? `${formatTime(range.start)} ~ ${formatTime(range.end)} 구간만 남기고 나머지 ${removed.toFixed(1)}초는 삭제합니다.
삭제한 부분은 복구할 수 없습니다. 계속하시겠습니까?`
        : `${count}개 구간을 각각 별도 클립으로 나눕니다.
원본은 휴지통으로 이동하며 휴지통에 보관하는 기간 안에는 복구할 수 있습니다. 계속하시겠습니까?`
    const result = await ask({ message, confirmLabel: count === 1 ? '자르기' : '나누기', danger: count === 1 })
    if (result.ok) onApply(ranges)
  }

  return (
    <div className="flex flex-col gap-2 rounded border border-sky-500/40 bg-zinc-800/80 p-3 text-sm text-zinc-200">
      <div className="relative h-8">
        <div className="absolute inset-x-0 top-1/2 h-2 -translate-y-1/2 rounded bg-zinc-700" />
        {ranges.map((r, i) => (
          <div
            key={i}
            className={`absolute top-1/2 h-4 -translate-y-1/2 cursor-pointer rounded ${i === active ? 'bg-sky-500/80' : 'bg-sky-500/35 hover:bg-sky-500/50'}`}
            style={{ left: pct(r.start), width: pct(r.end - r.start) }}
            onClick={() => setActive(i)}
          />
        ))}
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
          {count > 1 && `구간 ${active + 1}/${count} · `}남는 길이 {kept.toFixed(1)}초 · 삭제 {removed.toFixed(1)}초 (구간은 최소 {MIN_LENGTH}초 이상이며 서로 겹칠 수 없습니다)
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
        <button type="button" className="rounded border border-zinc-600 px-2 py-1 hover:bg-zinc-700 disabled:opacity-40" disabled={!canAdd} onClick={add}>
          + 구간 추가
        </button>
        {count > 1 && (
          <button type="button" className="rounded border border-zinc-600 px-2 py-1 hover:bg-zinc-700" onClick={() => remove(active)}>
            이 구간 빼기
          </button>
        )}
        <div className="ml-auto flex gap-2">
          <button type="button" className="rounded px-3 py-1 text-zinc-300 hover:bg-zinc-700" onClick={onCancel}>
            취소
          </button>
          <button
            type="button"
            className="rounded bg-rose-600 px-3 py-1 hover:bg-rose-500 disabled:opacity-40"
            disabled={busy || (count === 1 && removed < 0.05)}
            onClick={apply}
          >
            {busy ? '자르는 중...' : count === 1 ? '구간만 남기고 나머지 삭제' : `${count}개 클립으로 나누기`}
          </button>
        </div>
      </div>
    </div>
  )
}
