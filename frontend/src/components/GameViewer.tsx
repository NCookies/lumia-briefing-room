import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { candidateTitle, effectiveRange, formatClock, gameHeadline, isDismissed, isSaved, neighborCandidate, visibleCandidates, type Candidate, type GameDetail } from '../games'
import {
  GameNotFoundError,
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
import { EMPTY_HISTORY, pushEdit, redoStep, remapId, undoStep, type Edit } from '../editHistory'
import { applyMark, candidateAtTime, newRangeAround, rangeModified, zoomBy, zoomView, type View } from '../playerBar'
import { loadVolume, saveVolume, stepVolume, type VolumeState } from '../volume'
import { isLegacyWithoutVideo } from '../legacyGame'
import { isPlaybackFailure } from '../playback'
import { gameHeading } from '../gameEdit'
import { LegacyGamePanel } from './LegacyGamePanel'
import { ViewerBar, ViewerScroll } from './ViewerBar'
import { ExitFullscreenIcon, FullscreenIcon, MuteIcon, NextIcon, PauseIcon, PlayIcon, PrevIcon, SeekBackIcon, SeekForwardIcon, VolumeIcon, ZoomInIcon, ZoomOutIcon, UndoIcon, RedoIcon, KeyboardIcon, PlusIcon } from './ViewerIcons'
import { ArchivePopup } from './ArchivePopup'
import { SavedClipPlayer } from './SavedClipPlayer'
import { GameMenu, type GameMenuItem } from './GameMenu'
import { ViewerCandidates } from './ViewerCandidates'
import { ShortcutTable } from './ShortcutTable'
import { HelpTip } from './HelpTip'
import { fillHeight } from '../fillHeight'
import { SEEK_STEP_SEC, decideKey, isTextEntry, loadHelpSeen, saveHelpSeen, type TargetInfo, type ViewerAction } from '../viewerShortcuts'


const isModalOpen = () => document.querySelector('[role="dialog"], [role="menu"]') !== null

const targetInfo = (t: EventTarget | null): TargetInfo | null => {
  const el = t as HTMLElement | null
  return el && el.tagName ? { tag: el.tagName, type: (el as HTMLInputElement).type, editable: el.isContentEditable } : null
}

const SAVING = '저장 중…'

const LEGEND_HELP = '다시 저장을 눌러야 새 범위가 반영됩니다'

const BTN =
  'rounded-md border border-zinc-600/70 bg-zinc-800/60 px-2.5 py-1 text-sm text-zinc-200 transition hover:bg-zinc-700 hover:text-white active:scale-95 disabled:opacity-40 disabled:hover:bg-zinc-800/60'
const CTRL =
  'inline-flex h-8 items-center justify-center gap-1.5 rounded-md px-2.5 text-sm text-zinc-200 transition hover:bg-zinc-700/80 hover:text-white active:scale-95 disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-zinc-200'
const CTRL_ICON =
  'inline-flex h-8 w-8 items-center justify-center rounded-md text-zinc-200 transition hover:bg-zinc-700/80 hover:text-white active:scale-95 disabled:opacity-40 disabled:hover:bg-transparent'

export function GameViewer({
  gameKey,
  onBack,
  onChanged,
  backLabel = '← 게임 목록',
  menu,
  autoPlay = false,
  onMissing,
  active = true,
}: {
  gameKey: string
  onBack: () => void
  onChanged: () => void
  backLabel?: string
  /** 머리줄 `⋯` 메뉴(게임 삭제 등). */
  menu?: GameMenuItem[]
  /** 게임 행을 눌러 열었을 때 바로 재생한다. 브라우저가 막으면 일시정지로 두고 오류는 내지 않는다. */
  autoPlay?: boolean
  /** 열려는 게임이 없을 때(지워진 주소) 부른다. */
  onMissing?: () => void
  /** 이 화면이 속한 탭이 보이는 중인지. 탭을 바꿔도 화면은 마운트된 채라, 아니면 영상을 멈추고 단축키를 받지 않는다. */
  active?: boolean
}) {
  const [game, setGame] = useState<GameDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [busyText, setBusyText] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [videoError, setVideoError] = useState(false)
  const [time, setTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [zoomWindow, setZoomWindow] = useState<View | null>(null)
  const [history, setHistory] = useState(EMPTY_HISTORY)
  const [overrides, setOverrides] = useState<Record<string, [number, number]>>({})
  const [vol, setVol] = useState<VolumeState>(loadVolume)
  const [fullscreen, setFullscreen] = useState(false)
  const [volumeToast, setVolumeToast] = useState<number | null>(null)
  const toastTimer = useRef(0)
  const [showDismissed, setShowDismissed] = useState(false)
  const ask = useConfirm()
  const [memoOpenId, setMemoOpenId] = useState<string | null>(null)
  const [helpOpen, setHelpOpen] = useState(() => !loadHelpSeen())
  const root = useRef<HTMLDivElement>(null)
  const stage = useRef<HTMLDivElement>(null)
  const [stageHeight, setStageHeight] = useState<number | null>(null)
  const [archiveTarget, setArchiveTarget] = useState<{ id: string; anchor: DOMRect } | null>(null)
  const video = useRef<HTMLVideoElement>(null)
  const shell = useRef<HTMLDivElement>(null)
  const autoPlayed = useRef(false)
  const missing = useRef(onMissing)
  missing.current = onMissing

  const reload = useCallback(
    () =>
      getGame(gameKey)
        .then(setGame)
        .catch((e: Error) => {
          if (e instanceof GameNotFoundError && missing.current) missing.current()
          else setError(e.message)
        }),
    [gameKey],
  )

  useEffect(() => {
    void reload()
  }, [reload])

  useEffect(() => {
    if (!active) video.current?.pause()
  }, [active])

  useEffect(() => {
    if (helpOpen) saveHelpSeen()
  }, [helpOpen])

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

  const changeVolume = (direction: 1 | -1) => {
    const next = stepVolume(vol, direction)
    setVol(next)
    setVolumeToast(Math.round(next.volume * 100))
    window.clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => setVolumeToast(null), 1000)
  }

  const togglePlay = () => {
    const v = video.current
    if (!v) return
    if (v.paused) void v.play().catch((err: unknown) => setVideoError(isPlaybackFailure(err)))
    else v.pause()
  }

  const run = async (action: () => Promise<unknown>, done?: string, working = '처리 중…'): Promise<boolean> => {
    setBusy(true)
    setBusyText(working)
    setNotice(null)
    setError(null)
    try {
      await action()
      await reload()
      onChanged()
      if (done) setNotice(done)
      return true
    } catch (e) {
      setError((e as Error).message)
      return false
    } finally {
      setBusy(false)
      setBusyText(null)
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
    }, undefined, SAVING).finally(() => clearOverride(id))
  }

  const commitRange = (id: string, next: [number, number], prev: [number, number]) => {
    const saved = cands.find((c) => c.id === id)
    setRange(id, next, () => setHistory((h) => pushEdit(h, { kind: 'range', id, prev, next })))
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
    const step = busy ? null : undoStep(history)
    if (!step) return
    setHistory(step.history)
    const last = step.edit
    if (last.kind === 'range') setRange(last.id, last.prev)
    else if (last.kind === 'dismiss') void run(() => patchCandidate(gameKey, last.id, { dismissed: false }), '삭제한 후보를 되살렸습니다')
    else {
      setSelected(null)
      void run(() => deleteCandidate(gameKey, last.id))
    }
  }

  const redoLast = () => {
    const step = busy ? null : redoStep(history)
    if (!step) return
    setHistory(step.history)
    const next: Edit = step.edit
    if (next.kind === 'range') setRange(next.id, next.next)
    else if (next.kind === 'dismiss') {
      setSelected((sel) => (sel === next.id ? null : sel))
      void run(() => patchCandidate(gameKey, next.id, { dismissed: true }), '삭제했습니다')
    } else {
      void run(async () => {
        const created = await addCandidate(gameKey, next.range[0], next.range[1])
        setHistory((h) => remapId(h, next.id, created.id))
        setSelected(created.id)
      })
    }
  }

  const addHere = () => {
    if (busy || duration <= 0) return
    const [s, e] = newRangeAround(time, duration)
    void run(async () => {
      const created = await addCandidate(gameKey, s, e)
      setSelected(created.id)
      setHistory((h) => pushEdit(h, { kind: 'add', id: created.id, range: [s, e] }))
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
      void run(() => patchCandidate(gameKey, c.id, { dismissed: false }), '삭제한 후보를 되살렸습니다')
      return
    }
    if (c.id.includes('_u')) {
      void run(() => deleteCandidate(gameKey, c.id))
      return
    }
    setSelected((sel) => (sel === c.id ? null : sel))
    void run(async () => {
      await patchCandidate(gameKey, c.id, { dismissed: true })
      setHistory((h) => pushEdit(h, { kind: 'dismiss', id: c.id }))
    }, '후보를 삭제했습니다. Ctrl+Z 로 실행 취소할 수 있습니다')
  }

  const archive = (id: string, category?: string) => {
    setArchiveTarget(null)
    void run(
      async () => {
        const saved = await saveCandidate(gameKey, id, category)
        setNotice(saved.category ? `"${saved.category}"에 보관했습니다` : '보관했습니다')
      },
      undefined,
      '보관 중…',
    )
  }

  const resave = (id: string) => void run(() => saveCandidate(gameKey, id), '고친 범위를 보관한 클립에 저장했습니다', SAVING)

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
    }, undefined, SAVING)

  const openArchivePopup = (c: Candidate) => {
    if (busy || (!isSaved(c) && (!game?.hasFullVideo || isDismissed(c)))) return
    const row = document.querySelector(`[data-cand="${c.id}"]`)
    row?.scrollIntoView({ block: 'nearest' })
    const anchor =
      row?.querySelector('[data-archive-btn]')?.getBoundingClientRect() ??
      document.querySelector('[data-testid="viewer-candidates"]')?.getBoundingClientRect() ??
      new DOMRect(window.innerWidth - 340, 120, 0, 0)
    setArchiveTarget({ id: c.id, anchor })
  }

  const toggleMemo = () => {
    if (!selectedCand) return
    if (!isSaved(selectedCand)) {
      setNotice('메모는 보관한 클립에만 적을 수 있습니다 — 먼저 보관하세요')
      return
    }
    setMemoOpenId((open) => (open === selectedCand.id ? null : selectedCand.id))
  }

  const needsResave = (c: Candidate) => {
    const [start, end] = rangeOf(c)
    return isSaved(c) && rangeModified({ ...c, user: { ...c.user, start, end } }, duration)
  }

  const archivePopupWithSave = async (c: Candidate) => {
    if (busy) return
    if (needsResave(c) && !(await run(() => saveCandidate(gameKey, c.id), '고친 범위를 보관한 클립에 저장했습니다', SAVING))) return
    openArchivePopup(c)
  }

  const dispatch = (action: ViewerAction) => {
    switch (action) {
      case 'togglePlay':
        return togglePlay()
      case 'seekBack':
        return seek(time - SEEK_STEP_SEC)
      case 'seekForward':
        return seek(time + SEEK_STEP_SEC)
      case 'volumeUp':
        return changeVolume(1)
      case 'volumeDown':
        return changeVolume(-1)
      case 'fullscreen':
        return toggleFullscreen()
      case 'addSection':
        return addHere()
      case 'nextClip':
        return jump('next')
      case 'prevClip':
        return jump('prev')
      case 'archivePopup':
        return selectedCand && void archivePopupWithSave(selectedCand)
      case 'deleteClip':
        if (!selectedCand || busy || isDismissed(selectedCand)) return
        return isSaved(selectedCand) ? void deleteClip(selectedCand.id) : dismissOrDelete(selectedCand)
      case 'markStart':
        return mark('start')
      case 'markEnd':
        return mark('end')
      case 'undo':
        return undoLast()
      case 'redo':
        return redoLast()
      case 'memo':
        return toggleMemo()
      case 'help':
        return setHelpOpen((open) => !open)
    }
  }

  const handleKey = (e: KeyboardEvent) => {
    if (!active) return
    const modalOpen = isModalOpen()
    if (e.key === 'Escape' && helpOpen && !modalOpen) setHelpOpen(false)
    const decision = decideKey({
      key: e.key,
      code: e.code,
      ctrl: e.ctrlKey,
      meta: e.metaKey,
      alt: e.altKey,
      shift: e.shiftKey,
      repeat: e.repeat,
      textEntry: isTextEntry(targetInfo(e.target)),
      modalOpen,
    })
    if (!game?.hasFullVideo) {
      if (decision.preventDefault && (e.ctrlKey || e.metaKey)) e.preventDefault()
      return
    }
    if (decision.preventDefault) e.preventDefault()
    if (decision.action) dispatch(decision.action)
  }
  const keyRef = useRef(handleKey)
  keyRef.current = handleKey
  useEffect(() => {
    const down = (e: KeyboardEvent) => keyRef.current(e)
    const upSpace = (e: KeyboardEvent) => {
      if (e.key === ' ' && !isTextEntry(targetInfo(e.target)) && !isModalOpen()) e.preventDefault()
    }
    const releaseFocus = (e: MouseEvent) => {
      if (e.detail === 0) return
      const el = (e.target as HTMLElement | null)?.closest<HTMLElement>('button, input[type="checkbox"], input[type="range"], input[type="radio"]')
      if (el && root.current?.contains(el)) el.blur()
    }
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', upSpace)
    window.addEventListener('click', releaseFocus)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', upSpace)
      window.removeEventListener('click', releaseFocus)
    }
  }, [])

  const loaded = game !== null
  useLayoutEffect(() => {
    if (!active || !loaded) return
    const fit = () => {
      if (!stage.current) return
      setStageHeight(fillHeight({ top: stage.current.getBoundingClientRect().top + window.scrollY, viewportHeight: window.innerHeight, bottomGap: 16, min: 460 }))
    }
    fit()
    const observer = new ResizeObserver(fit)
    observer.observe(document.body)
    window.addEventListener('resize', fit)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', fit)
    }
  }, [active, loaded])

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
      saving={busyText === SAVING}
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
      memoOpenId={memoOpenId}
      onMemoOpenChange={setMemoOpenId}
    />
  )

  return (
    <div ref={root} className="flex flex-1 flex-col gap-2 p-4">
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-zinc-700/60 bg-zinc-800/60 px-3 py-2">
        <button type="button" className={BTN} onClick={onBack}>
          {backLabel}
        </button>
        <h2 className="text-lg font-semibold">{gameHeadline(game.matchResult, game.recordingStopped)}</h2>
        <span className={game.title ? 'text-sm font-medium text-zinc-200' : 'text-xs text-zinc-500'}>{gameHeading(game)}</span>
        {busyText && <span role="status" className="animate-pulse text-sm text-amber-300">{busyText}</span>}
        {error && <span className="text-sm text-rose-300">{error}</span>}
        {notice && <span className="text-sm text-emerald-300">{notice}</span>}
        <label className="ml-auto flex items-center gap-1 text-sm text-zinc-300">
          <input type="checkbox" checked={game.pinned} onChange={(e) => void run(() => setGamePinned(gameKey, e.target.checked))} />
          고정(자동 정리에서 제외)
        </label>
        {menu && menu.length > 0 && <GameMenu items={menu} />}
      </div>

      <div ref={stage} className="flex min-h-0 gap-3" style={{ height: stageHeight ?? undefined, minHeight: 460 }}>
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
          <div ref={shell} data-testid="viewer-shell" className="relative flex min-w-0 flex-1 flex-col gap-1 bg-zinc-900 [&:fullscreen]:p-3">
            <video
              ref={video}
              data-testid="viewer-video"
              className="min-h-0 w-full flex-1 cursor-pointer rounded bg-black object-contain"
              src={gameVideoUrl(gameKey)}
              preload="metadata"
              onClick={togglePlay}
              onPlay={() => setPlaying(true)}
              onPlaying={() => setVideoError(false)}
              onPause={() => setPlaying(false)}
              onEnded={() => setPlaying(false)}
              onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
              onLoadedMetadata={(e) => {
                e.currentTarget.volume = vol.volume
                e.currentTarget.muted = vol.muted
                if (autoPlay && !autoPlayed.current) {
                  autoPlayed.current = true
                  void e.currentTarget.play().catch((err: unknown) => setVideoError(isPlaybackFailure(err)))
                }
              }}
              onError={() => setVideoError(true)}
            />
            {volumeToast !== null && (
              <div role="status" className="pointer-events-none absolute left-3 top-3 z-10 rounded-md bg-black/70 px-3 py-1.5 text-sm font-medium tabular-nums text-white">
                볼륨 {volumeToast}%
              </div>
            )}
            {helpOpen && (
              <div
                data-testid="shortcut-help"
                className="absolute right-2 top-2 z-10 max-h-[70%] w-[26rem] max-w-[calc(100%-1rem)] overflow-y-auto rounded border border-zinc-600 bg-zinc-900/95 p-3 shadow-lg"
              >
                <div className="mb-2 flex items-center justify-between text-sm font-medium text-zinc-100">
                  단축키
                  <button type="button" className="rounded px-1.5 text-xs text-zinc-400 hover:bg-zinc-700" title="닫기 (? 또는 Esc)" onClick={() => setHelpOpen(false)}>
                    닫기
                  </button>
                </div>
                <ShortcutTable />
              </div>
            )}
            {videoError && (
              <p className="text-sm text-amber-300">
                이 브라우저에서 풀영상을 재생하지 못했습니다. 스팀 녹화(HEVC)라면 설치된 Edge/Chrome 에서 열거나 HEVC 확장을 설치해 주세요.
              </p>
            )}

            <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 rounded-lg border border-zinc-700/60 bg-zinc-800/60 px-2 py-1.5 text-white">
              <span className="inline-flex items-baseline gap-1 justify-self-start rounded-md bg-zinc-900/70 px-2.5 py-1 font-mono text-sm tabular-nums" aria-label="재생 위치">
                <span className="font-semibold text-sky-300">{formatClock(time)}</span>
                <span className="text-zinc-600">/</span>
                <span className="text-zinc-400">{formatClock(duration)}</span>
              </span>
              <span className="flex items-center gap-1">
                <button type="button" className={CTRL} title="이전 클립 (Ctrl+←)" onClick={() => jump('prev')}>
                  <PrevIcon /> 이전 클립
                </button>
                <span className="mx-1 h-5 w-px bg-zinc-700" aria-hidden="true" />
                <button type="button" className={CTRL_ICON} title={`${SEEK_STEP_SEC}초 뒤로 (←)`} aria-label={`${SEEK_STEP_SEC}초 뒤로`} onClick={() => seek(time - SEEK_STEP_SEC)}>
                  <SeekBackIcon seconds={SEEK_STEP_SEC} />
                </button>
                <button
                  type="button"
                  className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-sky-600 text-white shadow transition hover:bg-sky-500 active:scale-95"
                  title="재생/일시정지 (Space)"
                  aria-label="재생/일시정지"
                  onClick={togglePlay}
                >
                  {playing ? <PauseIcon /> : <PlayIcon />}
                </button>
                <button type="button" className={CTRL_ICON} title={`${SEEK_STEP_SEC}초 앞으로 (→)`} aria-label={`${SEEK_STEP_SEC}초 앞으로`} onClick={() => seek(time + SEEK_STEP_SEC)}>
                  <SeekForwardIcon seconds={SEEK_STEP_SEC} />
                </button>
                <span className="mx-1 h-5 w-px bg-zinc-700" aria-hidden="true" />
                <button type="button" className={CTRL} title="다음 클립 (Ctrl+→)" onClick={() => jump('next')}>
                  다음 클립 <NextIcon />
                </button>
              </span>
              <span className="flex items-center gap-1 justify-self-end">
                <button type="button" className={CTRL_ICON} title="음소거" aria-label="음소거" onClick={() => setVol({ ...vol, muted: !vol.muted })}>
                  {vol.muted || vol.volume === 0 ? <MuteIcon /> : <VolumeIcon />}
                </button>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  aria-label="볼륨"
                  value={vol.muted ? 0 : vol.volume}
                  className="w-24 accent-sky-400"
                  onChange={(e) => setVol({ volume: Number(e.target.value), muted: false })}
                />
                <button type="button" className={CTRL_ICON} title="전체화면 (F)" aria-label="전체화면" onClick={toggleFullscreen}>
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

            <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 pt-3">
              <span />
              <div className="flex items-center gap-1 rounded-lg border border-zinc-700/60 bg-zinc-800/60 px-1.5 py-1 text-white">
                <button type="button" className={CTRL} title="단축키 표 보기·닫기 (?)" aria-pressed={helpOpen} onClick={() => setHelpOpen((open) => !open)}>
                  <KeyboardIcon /> 단축키
                </button>
                <span className="mx-1 h-5 w-px bg-zinc-700" aria-hidden="true" />
                <button type="button" disabled={history.undo.length === 0 || busy} className={CTRL} title="실행 취소 (Ctrl+Z)" onClick={undoLast}>
                  <UndoIcon /> 실행 취소
                </button>
                <button type="button" disabled={history.redo.length === 0 || busy} className={CTRL} title="다시 시도 (Ctrl+Y)" onClick={redoLast}>
                  <RedoIcon /> 다시 시도
                </button>
                <span className="mx-1 h-5 w-px bg-zinc-700" aria-hidden="true" />
                <button type="button" disabled={!zoomWindow} className={CTRL_ICON} title="배율 축소" aria-label="배율 축소" onClick={() => zoomStep(2)}>
                  <ZoomOutIcon />
                </button>
                <button type="button" className={CTRL_ICON} title="배율 확대" aria-label="배율 확대" onClick={() => zoomStep(0.5)}>
                  <ZoomInIcon />
                </button>
                <button
                  type="button"
                  disabled={busy}
                  className="ml-1 inline-flex h-8 items-center gap-1.5 rounded-md bg-amber-500/90 px-3 text-sm font-semibold text-zinc-900 shadow transition hover:bg-amber-400 active:scale-95 disabled:opacity-40"
                  title="현재 위치에 구간 추가 (N)"
                  onClick={addHere}
                >
                  <PlusIcon /> 여기서 구간 추가
                </button>
              </div>
              <span className="flex min-w-0 items-center justify-end gap-1.5">
              <span className="min-w-0 truncate text-right text-xs text-zinc-500" title={selectedCand ? candidateTitle(selectedCand) : undefined}>
                {selectedCand
                  ? `선택: ${candidateTitle(selectedCand)}`
                  : '막대의 노란 구간을 눌러 선택'}
              </span>
              <HelpTip label="저장 안내" hover alignRight text={LEGEND_HELP} />
              </span>
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
