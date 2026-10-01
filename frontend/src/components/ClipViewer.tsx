import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { thumbnailUrl } from '../api'
import { cardHeadline, formatWhen } from '../clipArchive'
import { CLIP_VIEWER_ACTIONS, clipViewerAction, neighborClipId, rangeFixTarget, type ClipSource } from '../clipViewer'
import { fillHeight } from '../fillHeight'
import { formatClock } from '../games'
import { getClipSource } from '../gamesApi'
import type { LibraryClip } from '../libraryApi'
import { isPlaybackFailure } from '../playback'
import type { TrimRange } from '../trimming'
import { SEEK_STEP_SEC, decideKey, isTextEntry, loadHelpSeen, saveHelpSeen, shortcutGroupsFor, type TargetInfo, type ViewerAction } from '../viewerShortcuts'
import { loadVolume, saveVolume, stepVolume, type VolumeState } from '../volume'
import { ArchivePopup } from './ArchivePopup'
import { ClipMemoInput } from './ClipMemoInput'
import { ClipVideo } from './ClipVideo'
import { GameMenu, type GameMenuItem } from './GameMenu'
import { PortraitRow } from './PortraitRow'
import { TrimPanel } from './TrimPanel'
import { BTN, CTRL, ShortcutPanel, ViewerControlBar, VolumeToast } from './ViewerControls'
import { KeyboardIcon } from './ViewerIcons'

const SHORTCUT_GROUPS = shortcutGroupsFor(CLIP_VIEWER_ACTIONS)

const isModalOpen = () => document.querySelector('[role="dialog"], [role="menu"]') !== null

const targetInfo = (t: EventTarget | null): TargetInfo | null => {
  const el = t as HTMLElement | null
  return el && el.tagName ? { tag: el.tagName, type: (el as HTMLInputElement).type, editable: el.isContentEditable } : null
}

interface Props {
  /** 같은 카테고리의 클립(목록 순서). 이전/다음 클립과 오른쪽 목록이 이 순서를 쓴다. */
  clips: LibraryClip[]
  clip: LibraryClip
  category: string
  /** 이 화면이 속한 탭이 보이는 중인지. 탭을 바꿔도 화면은 마운트된 채라, 아니면 영상을 멈추고 단축키를 받지 않는다. */
  active: boolean
  /** 확인 창 등 화면 밖 대화상자가 떠 있다. 단축키를 받지 않는다. */
  paused: boolean
  onBack: () => void
  /** 풀영상 화면을 이 클립의 후보가 선택된 채로 연다(범위는 거기서 고친다). */
  onOpenGame: (tab: 'steam' | 'vod', gameKey: string, candidateId: string) => void
  onOpen: (clipId: string) => void
  onRename: (clip: LibraryClip, title: string) => void
  onMemo: (clip: LibraryClip, memo: string | null) => void
  onMove: (clip: LibraryClip, category: string) => void
  onExport: (clip: LibraryClip) => void
  onReveal: (clip: LibraryClip) => void
  onDelete: (clip: LibraryClip) => void
  onTrim: (clip: LibraryClip, ranges: TrimRange[]) => Promise<void>
}

/** 클립 탭의 재생 화면. 풀영상 화면과 같은 컨트롤 줄·단축키로 클립 하나를 보고, 오른쪽에 같은 카테고리의 클립 목록을 둔다. */
export function ClipViewer({ clips, clip, category, active, paused, onBack, onOpenGame, onOpen, onRename, onMemo, onMove, onExport, onReveal, onDelete, onTrim }: Props) {
  const [time, setTime] = useState(0)
  const [duration, setDuration] = useState(clip.durationSec)
  const [playing, setPlaying] = useState(false)
  const [vol, setVol] = useState<VolumeState>(loadVolume)
  const [volumeToast, setVolumeToast] = useState<number | null>(null)
  const [fullscreen, setFullscreen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(() => !loadHelpSeen())
  const [editingTitle, setEditingTitle] = useState(false)
  const [draftTitle, setDraftTitle] = useState('')
  const [trimming, setTrimming] = useState(false)
  const [trimBusy, setTrimBusy] = useState(false)
  const [moveAnchor, setMoveAnchor] = useState<DOMRect | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [source, setSource] = useState<{ clipId: string; value: ClipSource | null } | null>(null)
  const [stageHeight, setStageHeight] = useState<number | null>(null)
  const root = useRef<HTMLDivElement>(null)
  const stage = useRef<HTMLDivElement>(null)
  const shell = useRef<HTMLDivElement>(null)
  const video = useRef<HTMLVideoElement | null>(null)
  const toastTimer = useRef(0)
  const moveButton = useRef<HTMLButtonElement>(null)
  const ids = useMemo(() => clips.map((c) => c.id), [clips])
  const prevId = neighborClipId(ids, clip.id, 'prev')
  const nextId = neighborClipId(ids, clip.id, 'next')

  useEffect(() => {
    if (helpOpen) saveHelpSeen()
  }, [helpOpen])

  useEffect(() => {
    if (!active) video.current?.pause()
  }, [active])

  useEffect(() => {
    if (clip.unknownVideo) return
    let cancelled = false
    getClipSource(clip.id)
      .then((value) => !cancelled && setSource({ clipId: clip.id, value }))
      .catch(() => !cancelled && setSource({ clipId: clip.id, value: null }))
    return () => {
      cancelled = true
    }
  }, [clip.id, clip.unknownVideo])

  useEffect(() => {
    setTime(0)
    setDuration(clip.durationSec)
    setPlaying(false)
    setTrimming(false)
    setEditingTitle(false)
    setError(null)
  }, [clip.id, clip.durationSec])

  useEffect(() => {
    if (video.current) {
      video.current.volume = vol.volume
      video.current.muted = vol.muted
    }
    saveVolume(vol)
  }, [vol])

  useEffect(() => {
    const onChange = () => setFullscreen(document.fullscreenElement === shell.current && shell.current !== null)
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])

  useLayoutEffect(() => {
    if (!active) return
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
  }, [active])

  useEffect(() => {
    root.current?.querySelector(`[data-clip="${CSS.escape(clip.id)}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [clip.id])

  const seek = (t: number) => {
    const el = video.current
    if (!el) return
    const limit = Number.isFinite(el.duration) && el.duration > 0 ? el.duration : duration
    el.currentTime = Math.max(0, Math.min(limit, t))
    setTime(el.currentTime)
  }

  const togglePlay = () => {
    const el = video.current
    if (!el) return
    if (el.paused) void el.play().catch((e: unknown) => setError(isPlaybackFailure(e) ? '이 브라우저에서 클립을 재생하지 못했습니다.' : null))
    else el.pause()
  }

  const changeVolume = (direction: 1 | -1) => {
    const next = stepVolume(vol, direction)
    setVol(next)
    setVolumeToast(Math.round(next.volume * 100))
    window.clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => setVolumeToast(null), 1000)
  }

  const toggleFullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen()
    else void shell.current?.requestFullscreen()
  }

  const go = (id: string | null) => id && onOpen(id)

  const openMove = () => {
    const rect = moveButton.current?.getBoundingClientRect() ?? new DOMRect(window.innerWidth - 340, 120, 0, 0)
    setMoveAnchor(rect)
  }

  const focusMemo = () => root.current?.querySelector<HTMLTextAreaElement>('textarea[aria-label="클립 메모"]')?.focus()

  const dispatch = (action: ViewerAction) => {
    switch (action) {
      case 'togglePlay':
        return togglePlay()
      case 'seekBack':
        return seek((video.current?.currentTime ?? time) - SEEK_STEP_SEC)
      case 'seekForward':
        return seek((video.current?.currentTime ?? time) + SEEK_STEP_SEC)
      case 'volumeUp':
        return changeVolume(1)
      case 'volumeDown':
        return changeVolume(-1)
      case 'fullscreen':
        return toggleFullscreen()
      case 'prevClip':
        return go(prevId)
      case 'nextClip':
        return go(nextId)
      case 'archivePopup':
        return openMove()
      case 'deleteClip':
        return onDelete(clip)
      case 'memo':
        return focusMemo()
      case 'help':
        return setHelpOpen((open) => !open)
    }
  }

  const handleKey = (e: KeyboardEvent) => {
    if (!active || paused) return
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
    if (decision.preventDefault) e.preventDefault()
    const action = clipViewerAction(decision.action)
    if (action) dispatch(action)
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

  const startRename = () => {
    setDraftTitle(clip.title)
    setEditingTitle(true)
  }

  const commitRename = () => {
    if (!editingTitle) return
    setEditingTitle(false)
    const title = draftTitle.trim()
    if (title && title !== clip.title) onRename(clip, title)
  }

  const sourceLoaded = clip.unknownVideo ? true : source?.clipId === clip.id
  const target = rangeFixTarget(clip.unknownVideo || source?.clipId !== clip.id ? null : source.value)
  const menu: GameMenuItem[] = [{ label: '탐색기에서 열기', onSelect: () => onReveal(clip) }]
  if (sourceLoaded && target.kind === 'trim') menu.push({ label: '✂ 자르기·나누기', onSelect: () => setTrimming(true) })

  const headline = clip.unknownVideo ? null : cardHeadline(clip)

  return (
    <div ref={root} className="flex flex-1 flex-col gap-2 p-4" data-testid="clip-viewer">
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-zinc-700/60 bg-zinc-800/60 px-3 py-2">
        <button type="button" className={BTN} onClick={onBack}>
          ← {category}
        </button>
        {editingTitle ? (
          <input
            className="w-[28rem] max-w-full rounded-md border border-zinc-600/70 bg-zinc-900 px-2 py-0.5 text-lg text-zinc-100"
            aria-label="클립 제목"
            value={draftTitle}
            autoFocus
            onChange={(e) => setDraftTitle(e.target.value)}
            onBlur={commitRename}
            onKeyDown={(e) => {
              e.stopPropagation()
              if (e.key === 'Enter') commitRename()
              if (e.key === 'Escape') setEditingTitle(false)
            }}
          />
        ) : (
          <>
            <h2 className="min-w-0 truncate text-lg font-semibold" title={clip.title}>
              {clip.title}
            </h2>
            <button type="button" aria-label="이름 수정" title="이름 수정" className="rounded-md px-1.5 py-0.5 text-zinc-400 transition hover:bg-zinc-700 hover:text-zinc-100" onClick={startRename}>
              ✎
            </button>
          </>
        )}
        {error && <span className="text-sm text-rose-300">{error}</span>}
        <span className="ml-auto flex items-center gap-2">
          {target.kind === 'game' && (
            <button
              type="button"
              className={BTN}
              title="이 클립을 만든 게임의 풀영상 화면이 이 구간을 선택한 채로 열립니다. 범위는 거기서 손잡이를 끌어 고치고 다시 저장하세요"
              onClick={() => onOpenGame(target.tab, target.gameKey, target.candidateId)}
            >
              풀영상 보기·범위 고치기
            </button>
          )}
          <button type="button" className={BTN} onClick={() => onExport(clip)}>
            내보내기
          </button>
          <button type="button" className={`${BTN} border-rose-500/50 text-rose-300 hover:bg-rose-500/20`} title="삭제 (Delete)" onClick={() => onDelete(clip)}>
            삭제
          </button>
          <GameMenu label="클립 메뉴" items={menu} />
        </span>
      </div>

      <div ref={stage} className="flex min-h-0 gap-3" style={{ height: stageHeight ?? undefined, minHeight: 460 }}>
        <div ref={shell} data-testid="clip-viewer-shell" className="relative flex min-w-0 flex-1 flex-col gap-1 bg-zinc-900 [&:fullscreen]:p-3">
          <ClipVideo
            key={`${clip.id}-${clip.durationSec}`}
            clipId={clip.id}
            nextClipId={nextId}
            version={clip.durationSec}
            videoRef={(el) => {
              video.current = el
              if (!el) return
              el.volume = vol.volume
              el.muted = vol.muted
            }}
            onVolumeChange={() => {}}
            player={{
              onPlay: () => setPlaying(true),
              onPause: () => setPlaying(false),
              onToggle: togglePlay,
              onTime: (el) => {
                setTime(el.currentTime)
                if (Number.isFinite(el.duration) && el.duration > 0) setDuration(el.duration)
              },
            }}
          />
          {volumeToast !== null && <VolumeToast percent={volumeToast} />}
          {helpOpen && <ShortcutPanel groups={SHORTCUT_GROUPS} onClose={() => setHelpOpen(false)} />}

          <input
            type="range"
            aria-label="재생 위치 이동"
            min={0}
            max={Math.max(duration, 0.1)}
            step={0.1}
            value={Math.min(time, duration)}
            className="w-full accent-sky-400"
            onChange={(e) => seek(Number(e.target.value))}
          />

          <ViewerControlBar
            time={time}
            duration={duration}
            playing={playing}
            vol={vol}
            fullscreen={fullscreen}
            prevDisabled={!prevId}
            nextDisabled={!nextId}
            onPrev={() => go(prevId)}
            onNext={() => go(nextId)}
            onSeekBy={(delta) => seek((video.current?.currentTime ?? time) + delta)}
            onTogglePlay={togglePlay}
            onVolume={setVol}
            onToggleFullscreen={toggleFullscreen}
          />

          {trimming && (
            <TrimPanel
              key={`${clip.id}-${clip.durationSec}`}
              duration={clip.durationSec}
              getVideo={() => video.current}
              busy={trimBusy}
              onCancel={() => setTrimming(false)}
              onApply={async (ranges) => {
                setTrimBusy(true)
                try {
                  await onTrim(clip, ranges)
                  setTrimming(false)
                } catch (e) {
                  setError((e as Error).message)
                } finally {
                  setTrimBusy(false)
                }
              }}
            />
          )}

          <div className="grid grid-cols-[1fr_auto] items-start gap-3 pt-1">
            <div className="flex min-w-0 flex-col gap-2">
              <div className="flex flex-wrap items-center gap-3">
                {headline ? (
                  <>
                    <span className="text-base font-bold">{headline}</span>
                    {clip.matchStartUtc && <span className="text-xs text-zinc-500">{formatWhen(clip.matchStartUtc)}</span>}
                    <PortraitRow clip={clip} />
                  </>
                ) : (
                  <span className="rounded-md bg-zinc-700/90 px-1.5 text-xs text-zinc-200">앱 밖 영상</span>
                )}
                <button
                  ref={moveButton}
                  type="button"
                  className={BTN}
                  title="카테고리 옮기기 (Ctrl+S)"
                  aria-label={`카테고리 ${category} — 옮기기`}
                  onClick={openMove}
                >
                  📁 {category}
                </button>
              </div>
              <ClipMemoInput clipId={clip.id} value={clip.memo} rows={2} compact onSave={(memo) => onMemo(clip, memo)} />
            </div>
            <button type="button" className={CTRL} title="단축키 표 보기·닫기 (?)" aria-pressed={helpOpen} onClick={() => setHelpOpen((open) => !open)}>
              <KeyboardIcon /> 단축키
            </button>
          </div>
        </div>

        <aside className="flex w-80 shrink-0 flex-col overflow-hidden rounded-lg border border-zinc-700/60 bg-zinc-800/40" data-testid="clip-viewer-list">
          <div className="border-b border-zinc-700/60 px-3 py-2 text-xs text-zinc-400">
            {category} · 클립 {clips.length}개
          </div>
          <ul className="min-h-0 flex-1 overflow-y-auto">
            {clips.map((c) => (
              <li key={c.id} data-clip={c.id}>
                <button
                  type="button"
                  className={`flex w-full items-center gap-2 px-2 py-1.5 text-left transition hover:bg-zinc-700/70 ${c.id === clip.id ? 'bg-zinc-700' : ''}`}
                  aria-current={c.id === clip.id ? 'true' : undefined}
                  onClick={() => onOpen(c.id)}
                >
                  <span className="relative h-12 w-20 shrink-0 overflow-hidden rounded bg-zinc-900">
                    <img src={thumbnailUrl(c.id)} alt="" className="h-full w-full object-cover" loading="lazy" onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
                    {c.durationSec > 0 && <span className="absolute bottom-0.5 right-0.5 rounded bg-black/70 px-1 text-[10px] text-zinc-100">{formatClock(c.durationSec)}</span>}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{c.unknownVideo ? c.title : cardHeadline(c)}</span>
                    <span className="block truncate text-xs text-zinc-400" title={c.title}>
                      {c.unknownVideo ? '앱 밖 영상' : c.title}
                    </span>
                    {!c.unknownVideo && c.matchStartUtc && <span className="block text-[11px] text-zinc-500">{formatWhen(c.matchStartUtc)}</span>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </aside>
      </div>

      {moveAnchor && (
        <ArchivePopup
          title="카테고리 옮기기"
          createLabel="만들고 옮기기"
          anchor={moveAnchor}
          current={category}
          archived={false}
          onPick={(picked) => {
            setMoveAnchor(null)
            if (picked && picked !== category) onMove(clip, picked)
          }}
          onClose={() => setMoveAnchor(null)}
        />
      )}
    </div>
  )
}
