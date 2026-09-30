import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { formatBytes } from '../retention'
import { analysisBlockedReason, analysisPercent, formatDuration, vodStatusLabel, type Vod } from '../vodGrouping'
import { formatDateChip } from '../vodDates'
import type { AnalysisJob } from '../vodApi'

interface Props {
  name: string
  vod: Vod | null
  job: AnalysisJob | null
  expanded: boolean
  gameCount: number
  clipCount: number
  visibleGameCount: number
  clipBytes: number
  analysisBusy: boolean
  onToggle: () => void
  onAnalyze: (options: { force?: boolean; rebuild?: boolean }) => void
  onCancel: () => void
  onRenameStreamer: (streamer: string) => void
  onEditDate: (date: string) => void
  onDeleteClips: () => void
  onDeleteVod: () => void
  buildableCount?: number
  onBuildFullVideos?: () => void
  deletable?: boolean
  bytesLabel?: string
  emptyHint?: string
  children: ReactNode
}

const PHASE_LABELS: Record<string, string> = {
  decode: '화면 판독',
  games: '게임 정리',
  full: '풀영상 만들기',
  cut: '클립 만들기',
  done: '완료',
}

const STATUS_STYLES: Record<string, string> = {
  new: 'bg-zinc-700 text-zinc-300',
  analyzing: 'bg-sky-500/20 text-sky-300',
  interrupted: 'bg-amber-500/20 text-amber-300',
  cancelled: 'bg-amber-500/20 text-amber-300',
  error: 'bg-rose-500/20 text-rose-300',
  done: 'bg-emerald-500/20 text-emerald-300',
}

const MENU_WIDTH = 288

function ReanalyzeMenu({
  disabled,
  blockedReason,
  onAnalyze,
}: {
  disabled: boolean
  blockedReason: string
  onAnalyze: (options: { force?: boolean; rebuild?: boolean }) => void
}) {
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)
  const buttonRef = useRef<HTMLButtonElement | null>(null)
  const menuRef = useRef<HTMLDivElement | null>(null)

  const open = pos !== null

  useEffect(() => {
    if (!open) return
    const onDocMouseDown = (e: MouseEvent) => {
      const target = e.target as Node
      if (buttonRef.current?.contains(target) || menuRef.current?.contains(target)) return
      setPos(null)
    }
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setPos(null)
    }
    document.addEventListener('mousedown', onDocMouseDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onDocMouseDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const toggle = () => {
    if (open) {
      setPos(null)
      return
    }
    const rect = buttonRef.current?.getBoundingClientRect()
    if (!rect) return
    setPos({ top: rect.bottom + 4, left: Math.max(8, rect.right - MENU_WIDTH) })
  }

  const choose = (options: { force?: boolean; rebuild?: boolean }) => {
    setPos(null)
    onAnalyze(options)
  }

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        className="text-zinc-400 hover:text-sky-300 disabled:opacity-50"
        disabled={disabled}
        title={blockedReason}
        aria-expanded={open}
        onClick={toggle}
      >
        다시 분석
      </button>
      {open &&
        pos &&
        createPortal(
          // VodSection 이 overflow-hidden 이라 안에 그대로 두면 잘린다 - body 에 직접 붙인다.
          <div
            ref={menuRef}
            role="menu"
            className="fixed z-50 rounded border border-zinc-600 bg-zinc-800 p-3 text-left text-xs shadow-lg"
            style={{ top: pos.top, left: pos.left, width: MENU_WIDTH }}
          >
            <p className="mb-2 text-zinc-400">저장된 판독 결과가 있습니다. 어떻게 다시 만들까요?</p>
            <button
              type="button"
              role="menuitem"
              className="mb-1.5 block w-full rounded border border-zinc-600 px-2 py-1.5 text-left hover:border-sky-500 hover:bg-zinc-700"
              onClick={() => choose({ rebuild: true })}
            >
              <span className="block font-semibold text-sky-300">캐시 재사용 (빠름)</span>
              <span className="block text-zinc-400">
                화면 판독은 그대로 두고 클립만 다시 만듭니다. 필터·클립 구간 설정을 바꿨을 때 씁니다.
              </span>
            </button>
            <button
              type="button"
              role="menuitem"
              className="mb-1.5 block w-full rounded border border-zinc-600 px-2 py-1.5 text-left hover:border-sky-500 hover:bg-zinc-700"
              onClick={() => choose({ force: true })}
            >
              <span className="block font-semibold text-amber-300">처음부터 다시 (느림)</span>
              <span className="block text-zinc-400">
                화면 판독부터 다시 합니다. 원본 영상이 바뀌었거나 판독 결과가 의심될 때 씁니다.
              </span>
            </button>
            <button type="button" className="mt-0.5 text-zinc-500 hover:text-zinc-300" onClick={() => setPos(null)}>
              취소
            </button>
          </div>,
          document.body,
        )}
    </>
  )
}

function StreamerName({ value, onSave }: { value: string | null; onSave: (name: string) => void }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')

  if (editing) {
    return (
      <form
        className="flex items-center gap-1"
        onSubmit={(e) => {
          e.preventDefault()
          onSave(draft.trim())
          setEditing(false)
        }}
      >
        <input
          autoFocus
          className="w-32 rounded border border-zinc-600 bg-zinc-900 px-2 py-0.5 text-sm"
          value={draft}
          placeholder="이름"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === 'Escape' && setEditing(false)}
        />
        <button type="submit" className="text-xs text-sky-400 hover:underline">
          저장
        </button>
      </form>
    )
  }
  return (
    <button
      type="button"
      className="text-sm text-zinc-300 hover:text-sky-300"
      title="이름 변경"
      onClick={() => {
        setDraft(value ?? '')
        setEditing(true)
      }}
    >
      {value ? `${value} ✎` : '이름 지정 ✎'}
    </button>
  )
}

function VideoDate({ value, onSave }: { value: string | null; onSave: (date: string) => void }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')

  if (editing) {
    return (
      <form
        className="flex items-center gap-1"
        onSubmit={(e) => {
          e.preventDefault()
          if (draft) onSave(draft)
          setEditing(false)
        }}
      >
        <input
          autoFocus
          type="date"
          className="rounded border border-zinc-600 bg-zinc-900 px-2 py-0.5 text-sm"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === 'Escape' && setEditing(false)}
        />
        <button type="submit" className="text-xs text-sky-400 hover:underline">
          저장
        </button>
      </form>
    )
  }
  return (
    <button
      type="button"
      className="text-sm text-zinc-300 hover:text-sky-300"
      title="영상 날짜가 다르면 여기서 고칠 수 있습니다"
      onClick={() => {
        setDraft(value ?? '')
        setEditing(true)
      }}
    >
      {value ? `${formatDateChip(value)} ✎` : '날짜 지정 ✎'}
    </button>
  )
}

export function VodSection({
  name,
  vod,
  job,
  expanded,
  gameCount,
  clipCount,
  visibleGameCount,
  clipBytes,
  analysisBusy,
  onToggle,
  onAnalyze,
  onCancel,
  onRenameStreamer,
  onEditDate,
  onDeleteClips,
  onDeleteVod,
  buildableCount = 0,
  onBuildFullVideos,
  deletable,
  bytesLabel = '',
  emptyHint,
  children,
}: Props) {
  const running = vod?.status === 'analyzing'
  const buildingFullVideos = running && job?.kind === 'fullVideos'
  const percent = running ? Math.round((job?.fraction ?? 0) * 100) : vod ? analysisPercent(vod) : 0
  const resolution = vod?.width && vod.height ? `${vod.height}p` : ''
  const canStart = vod !== null && vod.exists && !analysisBusy
  const blockedReason = analysisBlockedReason(vod, analysisBusy)

  return (
    <section className="overflow-hidden rounded-xl border-2 border-zinc-600 bg-zinc-900/60">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 bg-zinc-800 px-4 py-3">
        <button
          type="button"
          className="flex min-w-0 flex-1 items-center gap-3 text-left"
          onClick={onToggle}
          aria-expanded={expanded}
        >
          <span className="text-lg text-zinc-400">{expanded ? '▼' : '▶'}</span>
          <span className="min-w-0">
            <span className="block truncate text-base font-semibold text-zinc-100" title={vod?.path}>
              {name}
            </span>
            <span className="block text-xs text-zinc-500">
              {[formatDuration(vod?.durationSec), resolution, vod?.sizeBytes ? formatBytes(vod.sizeBytes) : '']
                .filter(Boolean)
                .join(' · ')}
              {vod && !vod.exists && vod.sourceDeleted && (
                <span className="ml-2 text-zinc-500">설정에 따라 원본을 자동 삭제했습니다</span>
              )}
              {vod && !vod.exists && !vod.sourceDeleted && (
                <span className="ml-2 text-rose-400">영상 파일을 찾을 수 없습니다</span>
              )}
            </span>
          </span>
        </button>

        {vod && <VideoDate value={vod.videoDate} onSave={onEditDate} />}
        {vod && <StreamerName value={vod.streamer} onSave={onRenameStreamer} />}

        {vod && (
          <span className={`rounded px-2 py-0.5 text-xs ${STATUS_STYLES[vod.status]}`}>
            {vod.status === 'error' && vod.errorKind === 'disk_full'
              ? '저장 공간 부족으로 중단됨'
              : buildingFullVideos
                ? '풀영상 만드는 중'
                : vodStatusLabel(vod.status)}
            {vod.status !== 'done' && vod.status !== 'new' && percent > 0 ? ` ${percent}%` : ''}
          </span>
        )}

        <div className="text-right text-sm text-zinc-400">
          <div>
            게임 {gameCount}개 · 클립 {clipCount}개
          </div>
          <div className="text-xs text-zinc-500">
            {bytesLabel}
            {formatBytes(clipBytes)}
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs">
          {running ? (
            <button type="button" className="text-amber-300 hover:underline" onClick={onCancel}>
              {buildingFullVideos ? '취소' : '분석 취소'}
            </button>
          ) : vod && vod.status === 'done' ? (
            <ReanalyzeMenu disabled={!canStart} blockedReason={blockedReason} onAnalyze={onAnalyze} />
          ) : vod ? (
            <button
              type="button"
              className="rounded border border-sky-500/60 px-3 py-1 text-sky-300 hover:bg-sky-500/20 disabled:opacity-50"
              disabled={!canStart}
              title={blockedReason}
              onClick={() => onAnalyze({})}
            >
              {vod.status === 'new' ? '분석 시작' : '이어서 분석'}
            </button>
          ) : null}
          {!running && onBuildFullVideos && buildableCount > 0 && vod?.canBuildFullVideos && (
            <button
              type="button"
              className="rounded border border-sky-500/60 px-3 py-1 text-sky-300 hover:bg-sky-500/20 disabled:opacity-50"
              disabled={analysisBusy}
              title={
                analysisBusy
                  ? '다른 영상 작업이 끝나면 시작할 수 있습니다'
                  : '이전 버전에서 분석한 게임의 풀영상을 원본에서 잘라 만듭니다. 저장된 클립은 그대로 둡니다'
              }
              onClick={onBuildFullVideos}
            >
              풀영상 만들기 ({buildableCount})
            </button>
          )}
          {(deletable ?? clipCount > 0) && (
            <button type="button" className="text-zinc-400 hover:text-rose-400" onClick={onDeleteClips}>
              전체 삭제
            </button>
          )}
          {vod && !vod.exists && (
            <button
              type="button"
              className="text-zinc-400 hover:text-rose-400"
              title="원본 영상이 남아있으면 목록에서 지워도 다음에 다시 나타납니다"
              onClick={onDeleteVod}
            >
              목록에서 삭제
            </button>
          )}
        </div>
      </div>

      {running && (
        <div className="px-4 pb-3">
          <div className="h-2 overflow-hidden rounded bg-zinc-700">
            <div className="h-full bg-sky-500 transition-all" style={{ width: `${percent}%` }} />
          </div>
          <p className="mt-1 text-xs text-sky-300">
            {PHASE_LABELS[job?.phase ?? 'decode'] ?? ''} · {job?.message ?? ''}
            {job && (job.games ?? 0) > 0 ? ` · 게임 ${job.games}` : ''}
            {job && (job.clips ?? 0) > 0 ? ` · 클립 ${job.clips}` : ''}
          </p>
        </div>
      )}
      {vod?.status === 'error' && vod.error && <p className="px-4 pb-3 text-xs text-rose-400">{vod.error}</p>}
      {vod && (vod.status === 'interrupted' || vod.status === 'cancelled') && (
        <p className="px-4 pb-3 text-xs text-amber-300">
          {formatDuration(vod.analyzedSec)}까지 판독했습니다. 이어서 분석하면 그 지점부터 계속합니다.
        </p>
      )}

      {expanded && (
        <div className="flex flex-col gap-3 border-t border-zinc-700 p-3">
          {visibleGameCount === 0 && (
            <p className="px-1 text-center text-sm text-zinc-500">
              {emptyHint ??
                (vod?.status === 'done' ? '조건에 맞는 게임이 없습니다' : '아직 클립이 없습니다. 분석을 시작하면 게임별로 만들어집니다.')}
            </p>
          )}
          {children}
        </div>
      )}
    </section>
  )
}
