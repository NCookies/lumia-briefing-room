import { formatClock } from '../games'
import { SEEK_STEP_SEC, type ShortcutGroup } from '../viewerShortcuts'
import type { VolumeState } from '../volume'
import { ExitFullscreenIcon, FullscreenIcon, MuteIcon, NextIcon, PauseIcon, PlayIcon, PrevIcon, SeekBackIcon, SeekForwardIcon, VolumeIcon } from './ViewerIcons'
import { ShortcutTable } from './ShortcutTable'

export const BTN =
  'rounded-md border border-zinc-600/70 bg-zinc-800/60 px-2.5 py-1 text-sm text-zinc-200 transition hover:bg-zinc-700 hover:text-white active:scale-95 disabled:opacity-40 disabled:hover:bg-zinc-800/60'
export const CTRL =
  'inline-flex h-8 items-center justify-center gap-1.5 rounded-md px-2.5 text-sm text-zinc-200 transition hover:bg-zinc-700/80 hover:text-white active:scale-95 disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-zinc-200'
export const CTRL_ICON =
  'inline-flex h-8 w-8 items-center justify-center rounded-md text-zinc-200 transition hover:bg-zinc-700/80 hover:text-white active:scale-95 disabled:opacity-40 disabled:hover:bg-transparent'

interface ControlBarProps {
  time: number
  duration: number
  playing: boolean
  vol: VolumeState
  fullscreen: boolean
  onPrev: () => void
  onNext: () => void
  onSeekBy: (deltaSec: number) => void
  onTogglePlay: () => void
  onVolume: (next: VolumeState) => void
  onToggleFullscreen: () => void
  prevDisabled?: boolean
  nextDisabled?: boolean
}

/** 풀영상 화면과 클립 재생 화면이 같이 쓰는 컨트롤 줄: 시각 · 이전/뒤로/재생/앞으로/다음 · 음소거·볼륨·전체화면. */
export function ViewerControlBar({
  time,
  duration,
  playing,
  vol,
  fullscreen,
  onPrev,
  onNext,
  onSeekBy,
  onTogglePlay,
  onVolume,
  onToggleFullscreen,
  prevDisabled,
  nextDisabled,
}: ControlBarProps) {
  return (
    <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 rounded-lg border border-zinc-700/60 bg-zinc-800/60 px-2 py-1.5 text-white">
      <span className="inline-flex items-baseline gap-1 justify-self-start rounded-md bg-zinc-900/70 px-2.5 py-1 font-mono text-sm tabular-nums" aria-label="재생 위치">
        <span className="font-semibold text-sky-300">{formatClock(time)}</span>
        <span className="text-zinc-600">/</span>
        <span className="text-zinc-400">{formatClock(duration)}</span>
      </span>
      <span className="flex items-center gap-1">
        <button type="button" className={CTRL} disabled={prevDisabled} title="이전 클립 (Ctrl+←)" onClick={onPrev}>
          <PrevIcon /> 이전 클립
        </button>
        <span className="mx-1 h-5 w-px bg-zinc-700" aria-hidden="true" />
        <button type="button" className={CTRL_ICON} title={`${SEEK_STEP_SEC}초 뒤로 (←)`} aria-label={`${SEEK_STEP_SEC}초 뒤로`} onClick={() => onSeekBy(-SEEK_STEP_SEC)}>
          <SeekBackIcon seconds={SEEK_STEP_SEC} />
        </button>
        <button
          type="button"
          className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-sky-600 text-white shadow transition hover:bg-sky-500 active:scale-95"
          title="재생/일시정지 (Space)"
          aria-label="재생/일시정지"
          onClick={onTogglePlay}
        >
          {playing ? <PauseIcon /> : <PlayIcon />}
        </button>
        <button type="button" className={CTRL_ICON} title={`${SEEK_STEP_SEC}초 앞으로 (→)`} aria-label={`${SEEK_STEP_SEC}초 앞으로`} onClick={() => onSeekBy(SEEK_STEP_SEC)}>
          <SeekForwardIcon seconds={SEEK_STEP_SEC} />
        </button>
        <span className="mx-1 h-5 w-px bg-zinc-700" aria-hidden="true" />
        <button type="button" className={CTRL} disabled={nextDisabled} title="다음 클립 (Ctrl+→)" onClick={onNext}>
          다음 클립 <NextIcon />
        </button>
      </span>
      <span className="flex items-center gap-1 justify-self-end">
        <button type="button" className={CTRL_ICON} title="음소거" aria-label="음소거" onClick={() => onVolume({ ...vol, muted: !vol.muted })}>
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
          onChange={(e) => onVolume({ volume: Number(e.target.value), muted: false })}
        />
        <button type="button" className={CTRL_ICON} title="전체화면 (F)" aria-label="전체화면" onClick={onToggleFullscreen}>
          {fullscreen ? <ExitFullscreenIcon /> : <FullscreenIcon />}
        </button>
      </span>
    </div>
  )
}

export function VolumeToast({ percent }: { percent: number }) {
  return (
    <div role="status" className="pointer-events-none absolute left-3 top-3 z-10 rounded-md bg-black/70 px-3 py-1.5 text-sm font-medium tabular-nums text-white">
      볼륨 {percent}%
    </div>
  )
}

/** 영상 위에 겹쳐 뜨는 단축키 표. */
export function ShortcutPanel({ onClose, groups }: { onClose: () => void; groups?: ShortcutGroup[] }) {
  return (
    <div
      data-testid="shortcut-help"
      className="absolute right-2 top-2 z-10 max-h-[70%] w-[26rem] max-w-[calc(100%-1rem)] overflow-y-auto rounded border border-zinc-600 bg-zinc-900/95 p-3 shadow-lg"
    >
      <div className="mb-2 flex items-center justify-between text-sm font-medium text-zinc-100">
        단축키
        <button type="button" className="rounded px-1.5 text-xs text-zinc-400 hover:bg-zinc-700" title="닫기 (? 또는 Esc)" onClick={onClose}>
          닫기
        </button>
      </div>
      <ShortcutTable groups={groups} />
    </div>
  )
}
