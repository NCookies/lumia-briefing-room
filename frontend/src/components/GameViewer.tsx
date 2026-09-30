import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { effectiveRange, formatClock, gameHeadline, isDismissed, neighborCandidate, visibleCandidates, type Candidate, type GameDetail } from '../games'
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
import { applyMark, candidateAtTime, newRangeAround, zoomView, type View } from '../playerBar'
import { loadVolume, saveVolume, type VolumeState } from '../volume'
import { ViewerBar } from './ViewerBar'
import { ViewerCandidates } from './ViewerCandidates'

const SEEK_STEP_SEC = 5
const SKIP_SEC = 10

type Undo = { kind: 'range'; id: string; prev: [number, number] } | { kind: 'add'; id: string }

const BTN = 'rounded border border-zinc-600 px-2 py-1 text-sm hover:bg-zinc-700 disabled:opacity-40'

export function GameViewer({ gameKey, onBack, onChanged }: { gameKey: string; onBack: () => void; onChanged: () => void }) {
  const [game, setGame] = useState<GameDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [showDismissed, setShowDismissed] = useState(false)
  const [videoError, setVideoError] = useState(false)
  const [time, setTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [zoomed, setZoomed] = useState(false)
  const [undo, setUndo] = useState<Undo[]>([])
  const [overrides, setOverrides] = useState<Record<string, [number, number]>>({})
  const [vol, setVol] = useState<VolumeState>(loadVolume)
  const [fullscreen, setFullscreen] = useState(false)
  const video = useRef<HTMLVideoElement>(null)
  const shell = useRef<HTMLDivElement>(null)

  const reload = useCallback(
    () =>
      getGame(gameKey)
        .then(setGame)
        .catch((e: Error) => setError(e.message)),
    [gameKey],
  )

  useEffect(() => {
    void reload()
  }, [reload])

  const duration = game?.fullVideo?.durationSec ?? 0
  const cands = useMemo(() => (game ? visibleCandidates(game, showDismissed) : []), [game, showDismissed])
  const selectedCand = cands.find((c) => c.id === selected) ?? null
  const rangeOf = (c: Candidate): [number, number] => overrides[c.id] ?? effectiveRange(c, duration)
  const view: View = zoomed && selectedCand ? zoomView(effectiveRange(selectedCand, duration), duration) : [0, duration]
  const currentId = candidateAtTime(cands, time, duration)?.id ?? null

  const seek = (t: number) => {
    const clamped = Math.max(0, Math.min(duration, t))
    if (video.current) video.current.currentTime = clamped
    setTime(clamped)
  }

  useEffect(() => {
    if (!playing) return
    let raf = 0
    const tick = () => {
      if (video.current) setTime(video.current.currentTime)
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [playing])

  useEffect(() => {
    const v = video.current
    if (v) {
      v.volume = vol.volume
      v.muted = vol.muted
    }
    saveVolume(vol)
  }, [vol, game?.hasFullVideo])

  useEffect(() => {
    const onChange = () => setFullscreen(document.fullscreenElement === shell.current && shell.current !== null)
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])

  const toggleFullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen()
    else void shell.current?.requestFullscreen()
  }

  const togglePlay = () => {
    const v = video.current
    if (!v) return
    if (v.paused) void v.play().catch(() => setVideoError(true))
    else v.pause()
  }

  const run = async (action: () => Promise<unknown>, done?: string) => {
    setBusy(true)
    setNotice(null)
    setError(null)
    try {
      await action()
      await reload()
      onChanged()
      if (done) setNotice(done)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const clearOverride = (id: string) =>
    setOverrides((o) => {
      const next = { ...o }
      delete next[id]
      return next
    })

  const setRange = (id: string, next: [number, number], after?: () => void) => {
    setOverrides((o) => ({ ...o, [id]: next }))
    void run(async () => {
      await patchCandidate(gameKey, id, { start: next[0], end: next[1] })
      after?.()
    }).finally(() => clearOverride(id))
  }

  const commitRange = (id: string, next: [number, number], prev: [number, number]) =>
    setRange(id, next, () => setUndo((u) => [...u, { kind: 'range', id, prev }]))

  const mark = (kind: 'start' | 'end') => {
    if (!selectedCand || busy) return
    const prev = rangeOf(selectedCand)
    const next = applyMark(kind, prev, time, duration)
    if (next[0] !== prev[0] || next[1] !== prev[1]) commitRange(selectedCand.id, next, prev)
  }

  const undoLast = () => {
    const last = undo[undo.length - 1]
    if (!last || busy) return
    setUndo((u) => u.slice(0, -1))
    if (last.kind === 'range') setRange(last.id, last.prev)
    else {
      setSelected(null)
      void run(() => deleteCandidate(gameKey, last.id))
    }
  }

  const addHere = () => {
    if (busy || duration <= 0) return
    const [s, e] = newRangeAround(time, duration)
    void run(async () => {
      const created = await addCandidate(gameKey, s, e)
      setSelected(created.id)
      setUndo((u) => [...u, { kind: 'add', id: created.id }])
    }, '직접 구간을 추가했습니다 — 손잡이나 I/O 로 다듬으세요')
  }

  const select = (c: Candidate) => {
    setSelected(c.id)
    seek(rangeOf(c)[0])
  }

  const jump = (direction: 'prev' | 'next') => {
    if (!game) return
    const target = neighborCandidate(visibleCandidates(game), time, direction, duration)
    if (target) select(target)
  }

  const dismissOrDelete = (c: Candidate) => {
    if (c.id.includes('_u')) void run(() => deleteCandidate(gameKey, c.id))
    else void run(() => patchCandidate(gameKey, c.id, { dismissed: !isDismissed(c) }))
  }

  const saveOne = (id: string) => void run(() => saveCandidate(gameKey, id), '클립으로 저장했습니다')

  const batch = (mode: 'all' | 'certain' | 'ids') =>
    void run(async () => {
      const result = await saveBatch(gameKey, mode, mode === 'ids' ? [...checked] : undefined)
      setChecked(new Set())
      setNotice(
        `${result.saved.length}개 저장${result.failed.length ? `, ${result.failed.length}개 실패(${result.failed[0].error})` : ''}`,
      )
    })

  const toggleChecked = (id: string) =>
    setChecked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const handleKey = (e: KeyboardEvent) => {
    const target = e.target as HTMLElement | null
    if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT')) return
    if (e.ctrlKey || e.metaKey || e.altKey || !game?.hasFullVideo) return
    const key = e.key.length === 1 ? e.key.toLowerCase() : e.key
    const actions: Record<string, () => void> = {
      ' ': togglePlay,
      ArrowLeft: () => seek(time - SEEK_STEP_SEC),
      ArrowRight: () => seek(time + SEEK_STEP_SEC),
      n: () => jump('next'),
      p: () => jump('prev'),
      s: () => selectedCand && !busy && !isDismissed(selectedCand) && saveOne(selectedCand.id),
      d: () => selectedCand && !busy && dismissOrDelete(selectedCand),
      i: () => mark('start'),
      o: () => mark('end'),
    }
    const action = actions[key]
    if (!action) return
    e.preventDefault()
    action()
  }
  const keyRef = useRef(handleKey)
  keyRef.current = handleKey
  useEffect(() => {
    const down = (e: KeyboardEvent) => keyRef.current(e)
    const upSpace = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (e.key === ' ' && tag !== 'INPUT' && tag !== 'TEXTAREA') e.preventDefault()
    }
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', upSpace)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', upSpace)
    }
  }, [])

  if (!game) {
    return <p className="p-4 text-sm text-zinc-400">{error ?? '불러오는 중…'}</p>
  }

  const panel = (
    <ViewerCandidates
      cands={cands}
      duration={duration}
      selectedId={selected}
      currentId={currentId}
      checked={checked}
      showDismissed={showDismissed}
      busy={busy}
      canSave={game.hasFullVideo}
      onShowDismissed={setShowDismissed}
      onToggleChecked={toggleChecked}
      onSelect={select}
      onSave={saveOne}
      onDismiss={dismissOrDelete}
      onDelete={(id) => void run(() => deleteCandidate(gameKey, id))}
      onBatch={batch}
    />
  )

  return (
    <div className="flex flex-1 flex-col gap-2 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className={BTN} onClick={onBack}>
          ← 게임 목록
        </button>
        <h2 className="text-lg font-semibold">{gameHeadline(game.matchResult)}</h2>
        <span className="text-xs text-zinc-500">{game.gameKey}</span>
        {error && <span className="text-sm text-rose-300">{error}</span>}
        {notice && <span className="text-sm text-emerald-300">{notice}</span>}
        <label className="ml-auto flex items-center gap-1 text-sm text-zinc-300">
          <input type="checkbox" checked={game.pinned} onChange={(e) => void run(() => setGamePinned(gameKey, e.target.checked))} />
          고정(자동 정리에서 제외)
        </label>
      </div>

      <div className="flex min-h-0 gap-3" style={{ height: 'calc(100vh - 9.5rem)', minHeight: 460 }}>
        {!game.hasFullVideo ? (
          <p className="h-fit flex-1 rounded border border-amber-500/60 bg-amber-500/10 p-3 text-sm text-amber-200">
            {game.fullVideoError ?? '풀영상이 없습니다(자동 정리로 지워졌거나 저장하지 못했습니다).'} 후보 목록은 남아 있지만 영상을 볼 수
            없어 클립을 새로 저장할 수 없습니다.
          </p>
        ) : (
          <div ref={shell} data-testid="viewer-shell" className="flex min-w-0 flex-1 flex-col gap-1 bg-zinc-900 [&:fullscreen]:p-3">
            <video
              ref={video}
              data-testid="viewer-video"
              className="min-h-0 w-full flex-1 cursor-pointer rounded bg-black object-contain"
              src={gameVideoUrl(gameKey)}
              preload="metadata"
              onClick={togglePlay}
              onPlay={() => setPlaying(true)}
              onPause={() => setPlaying(false)}
              onEnded={() => setPlaying(false)}
              onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
              onLoadedMetadata={(e) => {
                e.currentTarget.volume = vol.volume
                e.currentTarget.muted = vol.muted
              }}
              onError={() => setVideoError(true)}
            />
            {videoError && (
              <p className="text-sm text-amber-300">
                이 브라우저에서 풀영상을 재생하지 못했습니다(HEVC). 설치된 Edge/Chrome 에서 열거나 HEVC 확장을 설치해 주세요.
              </p>
            )}

            <div className="flex flex-wrap items-center gap-1">
              <button type="button" className={BTN} title="재생/일시정지 (Space)" onClick={togglePlay}>
                {playing ? '⏸' : '▶'}
              </button>
              <button type="button" className={BTN} title="10초 뒤로" onClick={() => seek(time - SKIP_SEC)}>
                ↺10
              </button>
              <button type="button" className={BTN} title="10초 앞으로" onClick={() => seek(time + SKIP_SEC)}>
                10↻
              </button>
              <button type="button" className={BTN} title="이전 후보 (P)" onClick={() => jump('prev')}>
                ⏮ 후보
              </button>
              <button type="button" className={BTN} title="다음 후보 (N)" onClick={() => jump('next')}>
                후보 ⏭
              </button>
              <span className="ml-2 text-sm tabular-nums text-zinc-300">
                {formatClock(time)} / {formatClock(duration)}
              </span>
              <span className="ml-auto flex items-center gap-1">
                <button type="button" className={BTN} title="음소거" onClick={() => setVol({ ...vol, muted: !vol.muted })}>
                  {vol.muted || vol.volume === 0 ? '🔇' : '🔊'}
                </button>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  aria-label="볼륨"
                  value={vol.muted ? 0 : vol.volume}
                  className="w-20"
                  onChange={(e) => setVol({ volume: Number(e.target.value), muted: false })}
                />
                <button type="button" className={BTN} title="전체화면" onClick={toggleFullscreen}>
                  {fullscreen ? '⤡' : '⛶'}
                </button>
              </span>
            </div>

            <ViewerBar
              duration={duration}
              view={view}
              time={time}
              cands={cands}
              selectedId={selected}
              markers={game.markers}
              overrides={overrides}
              onSeek={seek}
              onSelect={setSelected}
              onRangeCommit={commitRange}
            />

            <div className="flex flex-wrap items-center gap-1 pt-1">
              <button type="button" disabled={!selectedCand || busy} className={BTN} title="선택한 구간의 시작을 현재 위치로 (I)" onClick={() => mark('start')}>
                시작점=현재 (I)
              </button>
              <button type="button" disabled={!selectedCand || busy} className={BTN} title="선택한 구간의 끝을 현재 위치로 (O)" onClick={() => mark('end')}>
                끝점=현재 (O)
              </button>
              <button type="button" disabled={undo.length === 0 || busy} className={BTN} onClick={undoLast}>
                되돌리기
              </button>
              <button
                type="button"
                disabled={!selectedCand}
                className={BTN}
                title="선택한 구간 앞뒤 30초를 막대 전체로 확대"
                onClick={() => setZoomed((z) => !z)}
              >
                {zoomed ? '전체 보기' : '확대'}
              </button>
              <button type="button" disabled={busy} className="rounded border border-yellow-600/60 px-2 py-1 text-sm hover:bg-zinc-700 disabled:opacity-40" onClick={addHere}>
                + 여기서 구간 추가
              </button>
              <span className="ml-2 truncate text-xs text-zinc-500">
                {selectedCand
                  ? `선택: ${selectedCand.title} — 노란 손잡이를 끌거나 I/O 로 범위 조정`
                  : '막대에서 노란 구간을 누르면 선택됩니다. 초록 킬 · 파랑 어시 · 빨강 사망 · 주황 팀원 사망'}
              </span>
            </div>
          </div>
        )}
        {panel}
      </div>
    </div>
  )
}
