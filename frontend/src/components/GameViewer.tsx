import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { candidateTitle, effectiveRange, formatClock, gameHeadline, isDismissed, isSaved, neighborCandidate, visibleCandidates, type Candidate, type GameDetail } from '../games'
import {
  addCandidate,
  deleteCandidate,
  gameVideoUrl,
  getGame,
  patchCandidate,
  saveCandidate,
  setGamePinned,
  unsaveCandidate,
} from '../gamesApi'
import { patchClip } from '../api'
import { useConfirm } from '../confirmContext'
import { moveClipsToCategory } from '../categoriesApi'
import { applyMark, candidateAtTime, newRangeAround, rangeModified, zoomBy, zoomView, type View } from '../playerBar'
import { loadVolume, saveVolume, type VolumeState } from '../volume'
import { isLegacyWithoutVideo } from '../legacyGame'
import { vodGameHeading } from '../vodGames'
import { LegacyGamePanel } from './LegacyGamePanel'
import { ViewerBar, ViewerScroll } from './ViewerBar'
import { ExitFullscreenIcon, FullscreenIcon, MuteIcon, NextIcon, PauseIcon, PlayIcon, PrevIcon, VolumeIcon, ZoomInIcon, ZoomOutIcon } from './ViewerIcons'
import { ArchivePopup } from './ArchivePopup'
import { SavedClipPlayer } from './SavedClipPlayer'
import { GameMenu, type GameMenuItem } from './GameMenu'
import { ViewerCandidates } from './ViewerCandidates'

const SEEK_STEP_SEC = 5
const SKIP_SEC = 10

type Undo = { kind: 'range'; id: string; prev: [number, number] } | { kind: 'add'; id: string } | { kind: 'dismiss'; id: string }

const BTN = 'rounded border border-zinc-600 px-2 py-1 text-sm hover:bg-zinc-700 disabled:opacity-40'

export function GameViewer({
  gameKey,
  onBack,
  onChanged,
  backLabel = '← 게임 목록',
  menu,
}: {
  gameKey: string
  onBack: () => void
  onChanged: () => void
  backLabel?: string
  /** 머리줄 `⋯` 메뉴(게임 삭제 등). */
  menu?: GameMenuItem[]
}) {
  const [game, setGame] = useState<GameDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [videoError, setVideoError] = useState(false)
  const [time, setTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [zoomWindow, setZoomWindow] = useState<View | null>(null)
  const [undo, setUndo] = useState<Undo[]>([])
  const [overrides, setOverrides] = useState<Record<string, [number, number]>>({})
  const [vol, setVol] = useState<VolumeState>(loadVolume)
  const [fullscreen, setFullscreen] = useState(false)
  const [showDismissed, setShowDismissed] = useState(false)
  const ask = useConfirm()
  const [archiveTarget, setArchiveTarget] = useState<{ id: string; anchor: DOMRect } | null>(null)
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
  const barCands = useMemo(() => cands.filter((c) => !isDismissed(c)), [cands])
  const selectedCand = cands.find((c) => c.id === selected) ?? null
  const noVideoClip = useMemo(
    () => (selectedCand?.user.savedClipId ? selectedCand : (cands.find((c) => c.user.savedClipId && !isDismissed(c)) ?? null)),
    [cands, selectedCand],
  )
  const rangeOf = (c: Candidate): [number, number] => overrides[c.id] ?? effectiveRange(c, duration)
  const view: View = zoomWindow ?? [0, duration]
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

  const commitRange = (id: string, next: [number, number], prev: [number, number]) => {
    const saved = cands.find((c) => c.id === id)
    setRange(id, next, () => setUndo((u) => [...u, { kind: 'range', id, prev }]))
    setNotice(
      saved && isSaved(saved)
        ? '범위를 수정했습니다 — 보관한 클립은 "다시 저장"을 눌러야 새 범위로 바뀝니다'
        : '범위를 수정했습니다 — 보관하면 이 범위로 클립이 만들어집니다',
    )
  }

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
    else if (last.kind === 'dismiss') void run(() => patchCandidate(gameKey, last.id, { dismissed: false }), '무시한 후보를 되살렸습니다')
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
    if (zoomWindow) setZoomWindow(zoomView(rangeOf(c), duration))
  }

  const jump = (direction: 'prev' | 'next') => {
    if (!game) return
    const target = neighborCandidate(visibleCandidates(game), time, direction, duration)
    if (target) select(target)
  }

  const dismissOrDelete = (c: Candidate) => {
    if (isDismissed(c)) {
      void run(() => patchCandidate(gameKey, c.id, { dismissed: false }), '무시한 후보를 되살렸습니다')
      return
    }
    if (c.id.includes('_u')) {
      void run(() => deleteCandidate(gameKey, c.id))
      return
    }
    setSelected((sel) => (sel === c.id ? null : sel))
    void run(async () => {
      await patchCandidate(gameKey, c.id, { dismissed: true })
      setUndo((u) => [...u, { kind: 'dismiss', id: c.id }])
    }, '후보를 무시했습니다 — Ctrl+Z 로 되돌릴 수 있습니다')
  }

  const archive = (id: string, category?: string) => {
    setArchiveTarget(null)
    void run(async () => {
      const saved = await saveCandidate(gameKey, id, category)
      setNotice(saved.category ? `"${saved.category}"에 보관했습니다` : '보관했습니다')
    })
  }

  const resave = (id: string) => void run(() => saveCandidate(gameKey, id), '고친 범위를 보관한 클립에 저장했습니다')

  const moveArchived = (id: string, category: string) => {
    const clipId = cands.find((c) => c.id === id)?.user.savedClipId
    setArchiveTarget(null)
    if (clipId) void run(() => moveClipsToCategory([clipId], category), `"${category}"로 옮겼습니다`)
  }

  const deleteClip = async (id: string) => {
    const cand = cands.find((c) => c.id === id)
    const result = await ask({
      message: `"${cand ? candidateTitle(cand) : '이'}" 클립을 삭제합니다.
클립 영상 파일과 이 구간(후보)이 목록에서 모두 사라지며 되돌릴 수 없습니다.`,
      confirmLabel: '삭제',
      danger: true,
    })
    if (!result.ok) return
    void run(() => unsaveCandidate(gameKey, id), '클립과 그 구간을 삭제했습니다')
  }

  const zoomStep = (factor: number) => {
    const base: View = zoomWindow ?? [0, duration]
    const center = time >= base[0] && time <= base[1] ? time : (base[0] + base[1]) / 2
    setZoomWindow(zoomBy(base, factor, center, duration))
  }

  const wheelZoom = (direction: 'in' | 'out', center: number) => {
    const base: View = zoomWindow ?? [0, duration]
    setZoomWindow(zoomBy(base, direction === 'in' ? 0.75 : 1 / 0.75, center, duration))
  }

  const modifiedIds = cands.filter((c) => isSaved(c) && !isDismissed(c) && rangeModified(c, duration)).map((c) => c.id)

  const saveModified = () =>
    void run(async () => {
      const failed: string[] = []
      for (const id of modifiedIds) {
        try {
          await saveCandidate(gameKey, id)
        } catch (e) {
          failed.push((e as Error).message)
        }
      }
      setNotice(`${modifiedIds.length - failed.length}개 저장했습니다${failed.length ? `, ${failed.length}개 실패(${failed[0]})` : ''}`)
    })

  const handleKey = (e: KeyboardEvent) => {
    const target = e.target as HTMLElement | null
    if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT')) return
    if (!game?.hasFullVideo) return
    if ((e.ctrlKey || e.metaKey) && e.code === 'KeyZ' && !e.shiftKey) {
      e.preventDefault()
      undoLast()
      return
    }
    if (e.ctrlKey || e.metaKey || e.altKey) return
    const key = e.key.length === 1 ? e.key.toLowerCase() : e.key
    const actions: Record<string, () => void> = {
      ' ': togglePlay,
      ArrowLeft: () => seek(time - SEEK_STEP_SEC),
      ArrowRight: () => seek(time + SEEK_STEP_SEC),
      n: () => jump('next'),
      p: () => jump('prev'),
      s: () =>
        selectedCand &&
        !busy &&
        !isDismissed(selectedCand) &&
        (!isSaved(selectedCand)
          ? archive(selectedCand.id)
          : rangeModified({ ...selectedCand, user: { ...selectedCand.user, start: rangeOf(selectedCand)[0], end: rangeOf(selectedCand)[1] } }, duration) &&
            resave(selectedCand.id)),
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
      modifiedCount={modifiedIds.length}
      busy={busy}
      canSave={game.hasFullVideo}
      onSelect={select}
      showDismissed={showDismissed}
      onToggleDismissed={setShowDismissed}
      onArchive={(id, anchor) => setArchiveTarget({ id, anchor })}
      onResave={resave}
      onDeleteClip={(id) => void deleteClip(id)}
      onMemo={(id, memo) => {
        const clipId = cands.find((c) => c.id === id)?.user.savedClipId
        if (clipId) void run(() => patchClip(clipId, { memo }))
      }}
      onDismiss={dismissOrDelete}
      onRename={(id, title) => void run(() => patchCandidate(gameKey, id, { title }))}
      onDelete={(id) => void run(() => deleteCandidate(gameKey, id))}
      onSaveModified={saveModified}
    />
  )

  return (
    <div className="flex flex-1 flex-col gap-2 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className={BTN} onClick={onBack}>
          {backLabel}
        </button>
        <h2 className="text-lg font-semibold">{gameHeadline(game.matchResult, game.recordingStopped)}</h2>
        <span className="text-xs text-zinc-500">{game.source === 'vod' ? vodGameHeading(game) : game.gameKey}</span>
        {error && <span className="text-sm text-rose-300">{error}</span>}
        {notice && <span className="text-sm text-emerald-300">{notice}</span>}
        <label className="ml-auto flex items-center gap-1 text-sm text-zinc-300">
          <input type="checkbox" checked={game.pinned} onChange={(e) => void run(() => setGamePinned(gameKey, e.target.checked))} />
          고정(자동 정리에서 제외)
        </label>
        {menu && menu.length > 0 && <GameMenu items={menu} />}
      </div>

      <div className="flex min-h-0 gap-3" style={{ height: 'calc(100vh - 9.5rem)', minHeight: 460 }}>
        {isLegacyWithoutVideo(game) ? (
          <LegacyGamePanel
            game={game}
            onRebuilt={() => {
              void reload()
              onChanged()
            }}
          />
        ) : !game.hasFullVideo ? (
          <SavedClipPlayer
            notice={`${game.fullVideoError ?? '풀영상이 없습니다(자동 정리로 지우거나 삭제했거나 만들지 못했습니다).'} 새로 보관할 수는 없지만, 이미 만든 클립은 오른쪽 목록에서 후보를 눌러 볼 수 있습니다.`}
            clipId={noVideoClip?.user.savedClipId ?? null}
            title={noVideoClip ? candidateTitle(noVideoClip) : null}
          />
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

            <div className="flex flex-wrap items-center gap-1 text-white">
              <button type="button" className={BTN} title="재생/일시정지 (Space)" onClick={togglePlay}>
                {playing ? <PauseIcon /> : <PlayIcon />}
              </button>
              <button type="button" className={BTN} title="10초 뒤로" onClick={() => seek(time - SKIP_SEC)}>
                ↺10
              </button>
              <button type="button" className={BTN} title="10초 앞으로" onClick={() => seek(time + SKIP_SEC)}>
                10↻
              </button>
              <button type="button" className={`${BTN} flex items-center gap-1`} title="이전 클립 (P)" onClick={() => jump('prev')}>
                <PrevIcon /> 이전 클립
              </button>
              <button type="button" className={`${BTN} flex items-center gap-1`} title="다음 클립 (N)" onClick={() => jump('next')}>
                다음 클립 <NextIcon />
              </button>
              <span className="ml-2 text-sm tabular-nums text-zinc-300">
                {formatClock(time)} / {formatClock(duration)}
              </span>
              <span className="ml-auto flex items-center gap-1">
                <button type="button" className={BTN} title="음소거" onClick={() => setVol({ ...vol, muted: !vol.muted })}>
                  {vol.muted || vol.volume === 0 ? <MuteIcon /> : <VolumeIcon />}
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
                  {fullscreen ? <ExitFullscreenIcon /> : <FullscreenIcon />}
                </button>
              </span>
            </div>

            <ViewerBar
              duration={duration}
              view={view}
              time={time}
              cands={barCands}
              selectedId={selected}
              markers={game.markers}
              overrides={overrides}
              onSeek={seek}
              onWheelZoom={wheelZoom}
              onSelect={setSelected}
              onRangeCommit={commitRange}
            />
            <ViewerScroll duration={duration} view={view} onPan={setZoomWindow} />

            <div className="flex items-center gap-2 pt-1">
              <span className="min-w-0 flex-1 truncate text-xs text-zinc-500">
                {selectedCand
                  ? `선택: ${candidateTitle(selectedCand)} — 양 끝 손잡이를 끌어 범위를 바꿉니다. 보관한 클립은 "다시 저장"을 눌러야 새 범위가 반영됩니다`
                  : '막대에서 노란 구간을 누르면 선택됩니다. 초록 킬 · 파랑 어시 · 빨강 사망 · 주황 팀원 사망'}
              </span>
              <div className="flex shrink-0 items-center gap-1 text-white">
                <button type="button" disabled={undo.length === 0 || busy} className={BTN} title="되돌리기 (Ctrl+Z)" onClick={undoLast}>
                  되돌리기
                </button>
                <button type="button" disabled={!zoomWindow} className={`${BTN} flex items-center`} title="배율 축소" onClick={() => zoomStep(2)}>
                  <ZoomOutIcon />
                </button>
                <button type="button" className={`${BTN} flex items-center`} title="배율 확대" onClick={() => zoomStep(0.5)}>
                  <ZoomInIcon />
                </button>
                <button type="button" disabled={busy} className="rounded border border-yellow-600/60 px-2 py-1 text-sm hover:bg-zinc-700 disabled:opacity-40" onClick={addHere}>
                  + 여기서 구간 추가
                </button>
              </div>
            </div>
          </div>
        )}
        {!isLegacyWithoutVideo(game) && panel}
        {archiveTarget &&
          (() => {
            const cand = cands.find((c) => c.id === archiveTarget.id)
            const hasClip = cand ? isSaved(cand) : false
            return (
              <ArchivePopup
                anchor={archiveTarget.anchor}
                current={cand?.user.savedCategory ?? null}
                archived={cand?.user.archived === true}
                onPick={(category) => (hasClip && category ? moveArchived(archiveTarget.id, category) : archive(archiveTarget.id, category))}
                onClose={() => setArchiveTarget(null)}
              />
            )
          })()}
      </div>
    </div>
  )
}
