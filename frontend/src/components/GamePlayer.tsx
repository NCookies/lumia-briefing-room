import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  MARKER_LABEL,
  MIN_RANGE_SEC,
  dragRange,
  effectiveRange,
  formatClock,
  gameHeadline,
  isDismissed,
  isSaved,
  neighborCandidate,
  positionPct,
  timeFromPointer,
  visibleCandidates,
  type Candidate,
  type DragKind,
  type GameDetail,
} from '../games'
import {
  addCandidate,
  deleteCandidate,
  gameVideoUrl,
  getGame,
  patchCandidate,
  saveBatch,
  saveCandidate,
  setGamePinned,
} from '../gamesApi'

interface Drag {
  kind: DragKind | 'create'
  id: string | null
  originX: number
  originTime: number
  base: [number, number]
  live: [number, number]
}

const MARKER_COLOR: Record<string, string> = {
  kill: 'bg-emerald-400',
  assist: 'bg-sky-400',
  death: 'bg-rose-500',
  teammate_death: 'bg-orange-400',
}

export function GamePlayer({ gameKey, onBack, onChanged }: { gameKey: string; onBack: () => void; onChanged: () => void }) {
  const [game, setGame] = useState<GameDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [showDismissed, setShowDismissed] = useState(false)
  const [videoError, setVideoError] = useState(false)
  const [time, setTime] = useState(0)
  const [drag, setDrag] = useState<Drag | null>(null)
  const video = useRef<HTMLVideoElement>(null)
  const bar = useRef<HTMLDivElement>(null)

  const reload = useCallback(() => {
    getGame(gameKey)
      .then(setGame)
      .catch((e: Error) => setError(e.message))
  }, [gameKey])

  useEffect(reload, [reload])

  const duration = game?.fullVideo?.durationSec ?? 0
  const cands = useMemo(() => (game ? visibleCandidates(game, showDismissed) : []), [game, showDismissed])

  const seek = (t: number) => {
    if (video.current) video.current.currentTime = Math.max(0, Math.min(duration, t))
  }

  const run = async (action: () => Promise<unknown>, done?: string) => {
    setBusy(true)
    setNotice(null)
    try {
      await action()
      reload()
      onChanged()
      if (done) setNotice(done)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const rangeOf = (c: Candidate): [number, number] =>
    drag && drag.id === c.id && drag.kind !== 'create' ? drag.live : effectiveRange(c, duration)

  const pointerTime = (clientX: number) => {
    const rect = bar.current?.getBoundingClientRect()
    return rect ? timeFromPointer(clientX, rect.left, rect.width, duration) : 0
  }

  const startDrag = (e: React.PointerEvent, kind: DragKind, c: Candidate) => {
    e.stopPropagation()
    e.preventDefault()
    const base = effectiveRange(c, duration)
    setSelected(c.id)
    setDrag({ kind, id: c.id, originX: e.clientX, originTime: pointerTime(e.clientX), base, live: base })
  }

  const startCreate = (e: React.PointerEvent) => {
    if (e.button !== 0 || duration <= 0) return
    const t = pointerTime(e.clientX)
    setDrag({ kind: 'create', id: null, originX: e.clientX, originTime: t, base: [t, t], live: [t, t] })
  }

  useEffect(() => {
    if (!drag) return
    const move = (e: PointerEvent) => {
      const now = pointerTime(e.clientX)
      if (drag.kind === 'create') {
        const [a, b] = now < drag.originTime ? [now, drag.originTime] : [drag.originTime, now]
        setDrag({ ...drag, live: [a, b] })
      } else {
        setDrag({ ...drag, live: dragRange(drag.kind, drag.base, now - drag.originTime, duration) })
      }
    }
    const up = () => {
      const { kind, id, live, base } = drag
      setDrag(null)
      if (kind === 'create') {
        if (live[1] - live[0] >= MIN_RANGE_SEC) void run(() => addCandidate(gameKey, live[0], live[1]), '직접 구간을 추가했습니다')
        else seek(live[0])
      } else if (id && (live[0] !== base[0] || live[1] !== base[1])) {
        void run(() => patchCandidate(gameKey, id, { start: live[0], end: live[1] }))
      }
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drag, duration, gameKey])

  const jump = (direction: 'prev' | 'next', certainOnly: boolean) => {
    if (!game) return
    const target = neighborCandidate(visibleCandidates(game), time, direction, duration, certainOnly)
    if (target) {
      setSelected(target.id)
      seek(effectiveRange(target, duration)[0])
    }
  }

  const toggleChecked = (id: string) =>
    setChecked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const batch = (mode: 'all' | 'certain' | 'ids') =>
    run(async () => {
      const result = await saveBatch(gameKey, mode, mode === 'ids' ? [...checked] : undefined)
      setChecked(new Set())
      setNotice(
        `${result.saved.length}개 저장${result.failed.length ? `, ${result.failed.length}개 실패(${result.failed[0].error})` : ''}`,
      )
    })

  if (!game) {
    return <p className="p-4 text-sm text-zinc-400">{error ?? '불러오는 중…'}</p>
  }

  const pending = cands.filter((c) => !isDismissed(c) && !isSaved(c))

  return (
    <div className="flex flex-1 flex-col gap-3 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="rounded-md border border-zinc-600/70 px-3 py-1 text-sm transition hover:bg-zinc-700" onClick={onBack}>
          ← 게임 목록
        </button>
        <h2 className="text-lg font-semibold">{gameHeadline(game.matchResult, game.recordingStopped)}</h2>
        <span className="text-xs text-zinc-500">{game.gameKey}</span>
        <label className="ml-auto flex items-center gap-1 text-sm text-zinc-300">
          <input
            type="checkbox"
            checked={game.pinned}
            onChange={(e) => void run(() => setGamePinned(gameKey, e.target.checked))}
          />
          고정(자동 정리에서 제외)
        </label>
      </div>

      {error && <p className="text-sm text-rose-300">{error}</p>}
      {notice && <p className="text-sm text-emerald-300">{notice}</p>}

      {!game.hasFullVideo ? (
        <p className="rounded-lg border border-amber-500/60 bg-amber-500/10 p-3 text-sm text-amber-200">
          {game.fullVideoError ?? '풀영상이 없습니다(자동 정리로 지워졌거나 저장하지 못했습니다).'} 후보 목록은 남아 있지만
          영상을 볼 수 없어 클립을 새로 저장할 수 없습니다.
        </p>
      ) : (
        <>
          <video
            ref={video}
            className="max-h-[55vh] w-full rounded-md bg-black"
            src={gameVideoUrl(gameKey)}
            controls
            preload="metadata"
            onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
            onError={() => setVideoError(true)}
          />
          {videoError && (
            <p className="text-sm text-amber-300">
              이 브라우저에서 풀영상을 재생하지 못했습니다(HEVC). 설치된 Edge/Chrome 에서 열거나 HEVC 확장을 설치해 주세요.
            </p>
          )}

          <div className="flex flex-wrap items-center gap-2 text-sm">
            <button type="button" className="rounded-md border border-zinc-600/70 px-2 py-1 transition hover:bg-zinc-700" onClick={() => jump('prev', false)}>
              ◀ 이전 후보
            </button>
            <button type="button" className="rounded-md border border-zinc-600/70 px-2 py-1 transition hover:bg-zinc-700" onClick={() => jump('next', false)}>
              다음 후보 ▶
            </button>
            <button type="button" className="rounded-md border border-yellow-600/60 px-2 py-1 transition hover:bg-zinc-700" onClick={() => jump('prev', true)}>
              ◀ 이전 확실한 후보
            </button>
            <button type="button" className="rounded-md border border-yellow-600/60 px-2 py-1 transition hover:bg-zinc-700" onClick={() => jump('next', true)}>
              다음 확실한 후보 ▶
            </button>
            <span className="ml-auto text-zinc-400">
              {formatClock(time)} / {formatClock(duration)}
            </span>
          </div>

          <div
            ref={bar}
            data-testid="timeline"
            className="relative h-14 cursor-crosshair select-none rounded-md bg-zinc-800"
            onPointerDown={startCreate}
          >
            {cands.map((c) => {
              const [s, e] = rangeOf(c)
              const active = selected === c.id
              return (
                <div
                  key={c.id}
                  className={`absolute top-1 bottom-1 rounded-sm ${
                    isDismissed(c)
                      ? 'bg-zinc-600/40'
                      : c.certain
                        ? 'bg-yellow-400/80'
                        : 'bg-yellow-300/30'
                  } ${active ? 'ring-2 ring-white' : ''}`}
                  style={{ left: `${positionPct(s, duration)}%`, width: `${Math.max(0.3, positionPct(e, duration) - positionPct(s, duration))}%` }}
                  title={`${c.title} ${formatClock(s)}~${formatClock(e)}`}
                  onPointerDown={(ev) => {
                    if (active) startDrag(ev, 'move', c)
                    else {
                      ev.stopPropagation()
                      setSelected(c.id)
                      seek(s)
                    }
                  }}
                >
                  {active && (
                    <>
                      <span
                        className="absolute inset-y-0 -left-1 w-2 cursor-ew-resize rounded-md bg-white"
                        onPointerDown={(ev) => startDrag(ev, 'start', c)}
                      />
                      <span
                        className="absolute inset-y-0 -right-1 w-2 cursor-ew-resize rounded-md bg-white"
                        onPointerDown={(ev) => startDrag(ev, 'end', c)}
                      />
                    </>
                  )}
                </div>
              )
            })}
            {game.markers.map((m, i) => (
              <span
                key={`${m.kind}-${i}`}
                className={`pointer-events-none absolute bottom-0 h-3 w-1 rounded-t ${MARKER_COLOR[m.kind] ?? 'bg-zinc-300'}`}
                style={{ left: `${positionPct(m.t, duration)}%` }}
                title={`${MARKER_LABEL[m.kind]} ${formatClock(m.t)}`}
              />
            ))}
            {drag?.kind === 'create' && (
              <div
                className="pointer-events-none absolute top-1 bottom-1 rounded-sm border border-white bg-white/20"
                style={{
                  left: `${positionPct(drag.live[0], duration)}%`,
                  width: `${positionPct(drag.live[1], duration) - positionPct(drag.live[0], duration)}%`,
                }}
              />
            )}
            <span
              className="pointer-events-none absolute inset-y-0 w-0.5 bg-rose-400"
              style={{ left: `${positionPct(time, duration)}%` }}
            />
          </div>
          <p className="text-xs text-zinc-500">
            노란색 진한 구간 = 킬·어시스트·사망이 있는 확실한 후보, 옅은 구간 = 그 밖의 후보. 구간을 누르면 선택되고 양 끝 흰
            핸들을 끌어 범위를 조정합니다. 빈 곳을 끌면 직접 구간을 추가합니다. 아래 막대: 초록 킬 · 파랑 어시스트 · 빨강
            사망 · 주황 팀원 사망.
          </p>
        </>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-base font-medium">후보 {pending.length}개 저장 대기</h3>
        <label className="ml-2 flex items-center gap-1 text-xs text-zinc-400">
          <input type="checkbox" checked={showDismissed} onChange={(e) => setShowDismissed(e.target.checked)} />
          무시한 후보도 보기
        </label>
        <div className="ml-auto flex flex-wrap gap-2 text-sm">
          <button type="button" disabled={busy || !game.hasFullVideo} className="rounded-md bg-sky-600 px-3 py-1 transition hover:bg-sky-500 disabled:opacity-40" onClick={() => void batch('all')}>
            전부 저장
          </button>
          <button type="button" disabled={busy || !game.hasFullVideo} className="rounded-md bg-sky-700 px-3 py-1 transition hover:bg-sky-600 disabled:opacity-40" onClick={() => void batch('certain')}>
            확실한 것만 저장
          </button>
          <button type="button" disabled={busy || !game.hasFullVideo || checked.size === 0} className="rounded-md border border-sky-600 px-3 py-1 transition hover:bg-zinc-700 disabled:opacity-40" onClick={() => void batch('ids')}>
            선택한 {checked.size}개 저장
          </button>
        </div>
      </div>

      <ul className="flex flex-col gap-1">
        {cands.length === 0 && <li className="text-sm text-zinc-500">교전 후보가 없습니다. 타임라인의 빈 곳을 끌어 직접 추가할 수 있습니다.</li>}
        {cands.map((c) => {
          const [s, e] = effectiveRange(c, duration)
          const saved = isSaved(c)
          const dismissed = isDismissed(c)
          return (
            <li
              key={c.id}
              className={`flex flex-wrap items-center gap-2 rounded-md border px-3 py-1.5 text-sm ${
                selected === c.id ? 'border-white bg-zinc-800' : 'border-zinc-700'
              } ${dismissed ? 'opacity-50' : ''}`}
            >
              <input
                type="checkbox"
                disabled={saved || dismissed}
                checked={checked.has(c.id)}
                onChange={() => toggleChecked(c.id)}
              />
              <button
                type="button"
                className="text-left hover:underline"
                onClick={() => {
                  setSelected(c.id)
                  seek(s)
                }}
              >
                {c.title}
              </button>
              <span className="text-xs text-zinc-400">
                {formatClock(s)}~{formatClock(e)} ({Math.round(e - s)}초)
              </span>
              {c.certain && <span className="rounded-md bg-yellow-500/20 px-1.5 text-xs text-yellow-300">확실</span>}
              {c.tags.map((t) => (
                <span key={t} className="rounded-md bg-zinc-700 px-1.5 text-xs text-zinc-300">
                  {t}
                </span>
              ))}
              <span className="ml-auto flex gap-1">
                {saved ? (
                  <span className="rounded-md bg-emerald-600/30 px-2 py-0.5 text-xs text-emerald-200">저장됨</span>
                ) : (
                  <button
                    type="button"
                    disabled={busy || !game.hasFullVideo || dismissed}
                    className="rounded-md bg-sky-600 px-2 py-0.5 text-xs transition hover:bg-sky-500 disabled:opacity-40"
                    onClick={() => void run(() => saveCandidate(gameKey, c.id), '클립으로 저장했습니다')}
                  >
                    저장
                  </button>
                )}
                {c.id.includes('_u') ? (
                  <button type="button" disabled={busy} className="rounded-md border border-zinc-600/70 px-2 py-0.5 text-xs transition hover:bg-zinc-700" onClick={() => void run(() => deleteCandidate(gameKey, c.id))}>
                    삭제
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled={busy || saved}
                    className="rounded-md border border-zinc-600/70 px-2 py-0.5 text-xs transition hover:bg-zinc-700 disabled:opacity-40"
                    onClick={() => void run(() => patchCandidate(gameKey, c.id, { dismissed: !dismissed }))}
                  >
                    {dismissed ? '되살리기' : '무시'}
                  </button>
                )}
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
