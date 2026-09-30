import { useEffect, useRef, useState } from 'react'
import { MARKER_LABEL, dragRange, effectiveRange, formatClock, isDismissed, type Candidate, type DragKind, type Marker } from '../games'
import { barPct, candidateAtTime, tickStep, timeFromBar, type View } from '../playerBar'

const MARKER_COLOR: Record<string, string> = {
  kill: 'bg-emerald-400',
  assist: 'bg-sky-300',
  death: 'bg-rose-500',
  teammate_death: 'bg-orange-400',
}

interface HandleDrag {
  kind: DragKind
  id: string
  originTime: number
  base: [number, number]
  live: [number, number]
}

interface Props {
  duration: number
  view: View
  time: number
  cands: Candidate[]
  selectedId: string | null
  markers: Marker[]
  overrides: Record<string, [number, number]>
  onSeek: (t: number) => void
  onSelect: (id: string) => void
  onRangeCommit: (id: string, next: [number, number], prev: [number, number]) => void
}

export function ViewerBar({ duration, view, time, cands, selectedId, markers, overrides, onSeek, onSelect, onRangeCommit }: Props) {
  const bar = useRef<HTMLDivElement>(null)
  const [scrubbing, setScrubbing] = useState(false)
  const [drag, setDrag] = useState<HandleDrag | null>(null)
  const [hover, setHover] = useState<number | null>(null)

  const pointerTime = (clientX: number) => {
    const rect = bar.current?.getBoundingClientRect()
    return rect ? timeFromBar(clientX, rect.left, rect.width, view) : 0
  }

  const rangeOf = (c: Candidate): [number, number] =>
    drag && drag.id === c.id ? drag.live : (overrides[c.id] ?? effectiveRange(c, duration))

  useEffect(() => {
    if (!scrubbing) return
    const move = (e: PointerEvent) => onSeek(pointerTime(e.clientX))
    const up = () => setScrubbing(false)
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scrubbing, view, duration])

  useEffect(() => {
    if (!drag) return
    const move = (e: PointerEvent) => {
      const delta = pointerTime(e.clientX) - drag.originTime
      setDrag({ ...drag, live: dragRange(drag.kind, drag.base, delta, duration) })
    }
    const up = () => {
      const { id, live, base } = drag
      setDrag(null)
      if (live[0] !== base[0] || live[1] !== base[1]) onRangeCommit(id, live, base)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drag, view, duration])

  const press = (e: React.PointerEvent) => {
    if (e.button !== 0 || duration <= 0) return
    const t = pointerTime(e.clientX)
    onSeek(t)
    const hit = candidateAtTime(cands, t, duration)
    if (hit) onSelect(hit.id)
    setScrubbing(true)
  }

  const startHandle = (e: React.PointerEvent, kind: DragKind, c: Candidate) => {
    e.stopPropagation()
    e.preventDefault()
    const base = rangeOf(c)
    setDrag({ kind, id: c.id, originTime: pointerTime(e.clientX), base, live: base })
  }

  const step = tickStep(view[1] - view[0])
  const ticks: number[] = []
  for (let t = Math.ceil(view[0] / step) * step; t <= view[1]; t += step) ticks.push(t)

  const hovered = hover === null ? null : candidateAtTime(cands, hover, duration)
  const pinVisible = time >= view[0] && time <= view[1]

  return (
    <div
      ref={bar}
      data-testid="viewer-bar"
      className="relative h-16 touch-none cursor-pointer select-none"
      onPointerDown={press}
      onPointerMove={(e) => setHover(pointerTime(e.clientX))}
      onPointerLeave={() => setHover(null)}
    >
      {ticks.map((t) => (
        <span
          key={t}
          className="pointer-events-none absolute top-0 -translate-x-1/2 text-[10px] leading-4 text-zinc-500"
          style={{ left: `${barPct(t, view)}%` }}
        >
          {formatClock(t)}
        </span>
      ))}
      <div className="absolute inset-x-0 top-5 h-8">
        <div className="absolute inset-x-0 top-3 h-2 rounded bg-sky-600" />
        {cands.map((c) => {
          const [s, e] = rangeOf(c)
          if (e < view[0] || s > view[1]) return null
          const active = selectedId === c.id
          const dismissed = isDismissed(c)
          const left = barPct(s, view)
          return (
            <div
              key={c.id}
              data-testid={`bar-cand-${c.id}`}
              className={`absolute inset-y-0 border-x-2 border-dashed ${
                dismissed ? 'border-zinc-400 bg-zinc-500/30' : c.certain ? 'border-yellow-300 bg-yellow-400/70' : 'border-yellow-300 bg-yellow-300/30'
              } ${active ? 'border-y border-y-white' : ''}`}
              style={{ left: `${left}%`, width: `${Math.max(0.3, barPct(e, view) - left)}%` }}
            >
              {active && s >= view[0] && (
                <span
                  data-testid="handle-start"
                  className="absolute -top-1 -bottom-1 -left-2 w-2 cursor-ew-resize rounded-l-sm border border-white bg-yellow-400"
                  onPointerDown={(ev) => startHandle(ev, 'start', c)}
                />
              )}
              {active && e <= view[1] && (
                <span
                  data-testid="handle-end"
                  className="absolute -top-1 -bottom-1 -right-2 w-2 cursor-ew-resize rounded-r-sm border border-white bg-yellow-400"
                  onPointerDown={(ev) => startHandle(ev, 'end', c)}
                />
              )}
            </div>
          )
        })}
      </div>
      {markers.map((m, i) =>
        m.t < view[0] || m.t > view[1] ? null : (
          <span
            key={`${m.kind}-${i}`}
            className={`pointer-events-none absolute bottom-0 h-2 w-1 -translate-x-1/2 rounded-b ${MARKER_COLOR[m.kind] ?? 'bg-zinc-300'}`}
            style={{ left: `${barPct(m.t, view)}%` }}
            title={`${MARKER_LABEL[m.kind]} ${formatClock(m.t)}`}
          />
        ),
      )}
      {pinVisible && (
        <span
          data-testid="viewer-pin"
          className="pointer-events-none absolute inset-y-0 z-10 w-0.5 -translate-x-1/2 bg-white"
          style={{ left: `${barPct(time, view)}%` }}
        >
          <span className="absolute -top-0.5 left-1/2 h-3 w-3 -translate-x-1/2 rounded-full bg-white shadow" />
        </span>
      )}
      {hover !== null && !drag && (
        <span
          className="pointer-events-none absolute -top-8 z-20 -translate-x-1/2 whitespace-nowrap rounded bg-black/85 px-2 py-0.5 text-xs text-zinc-100"
          style={{ left: `${barPct(hover, view)}%` }}
        >
          {formatClock(hover)}
          {hovered && ` · ${hovered.title}`}
        </span>
      )}
    </div>
  )
}
