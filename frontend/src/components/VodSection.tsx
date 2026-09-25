import { useState, type ReactNode } from 'react'
import { formatBytes } from '../retention'
import { analysisBlockedReason, analysisPercent, formatDuration, vodStatusLabel, type Vod } from '../vodGrouping'
import type { AnalysisJob } from '../vodApi'

interface Props {
  name: string
  vod: Vod | null
  job: AnalysisJob | null
  expanded: boolean
  trashed: boolean
  gameCount: number
  clipCount: number
  visibleClipCount: number
  clipBytes: number
  analysisBusy: boolean
  onToggle: () => void
  onAnalyze: (options: { force?: boolean; rebuild?: boolean }) => void
  onCancel: () => void
  onRenameStreamer: (streamer: string) => void
  onTrashClips: () => void
  onRestoreClips: () => void
  onDeleteClipsForever: () => void
  children: ReactNode
}

const PHASE_LABELS: Record<string, string> = {
  decode: '화면 판독',
  games: '게임 정리',
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
          placeholder="스트리머 이름"
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
      title="스트리머 이름 수정"
      onClick={() => {
        setDraft(value ?? '')
        setEditing(true)
      }}
    >
      {value ? `${value} ✎` : '이름 지정 ✎'}
    </button>
  )
}

export function VodSection({
  name,
  vod,
  job,
  expanded,
  trashed,
  gameCount,
  clipCount,
  visibleClipCount,
  clipBytes,
  analysisBusy,
  onToggle,
  onAnalyze,
  onCancel,
  onRenameStreamer,
  onTrashClips,
  onRestoreClips,
  onDeleteClipsForever,
  children,
}: Props) {
  const running = vod?.status === 'analyzing'
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
              {vod && !vod.exists && <span className="ml-2 text-rose-400">영상 파일을 찾을 수 없습니다</span>}
            </span>
          </span>
        </button>

        {!trashed && vod && <StreamerName value={vod.streamer} onSave={onRenameStreamer} />}

        {vod && !trashed && (
          <span className={`rounded px-2 py-0.5 text-xs ${STATUS_STYLES[vod.status]}`}>
            {vodStatusLabel(vod.status)}
            {vod.status !== 'done' && vod.status !== 'new' && percent > 0 ? ` ${percent}%` : ''}
          </span>
        )}

        <div className="text-right text-sm text-zinc-400">
          <div>
            게임 {gameCount}개 · 클립 {clipCount}개
          </div>
          <div className="text-xs text-zinc-500">{formatBytes(clipBytes)}</div>
        </div>

        <div className="flex items-center gap-3 text-xs">
          {trashed ? (
            <>
              <button type="button" className="text-sky-400 hover:underline" onClick={onRestoreClips}>
                영상 클립 복구
              </button>
              <button type="button" className="text-rose-400 hover:underline" onClick={onDeleteClipsForever}>
                영상 클립 완전 삭제
              </button>
            </>
          ) : (
            <>
              {running ? (
                <button type="button" className="text-amber-300 hover:underline" onClick={onCancel}>
                  분석 취소
                </button>
              ) : vod && vod.status === 'done' ? (
                <>
                  <button
                    type="button"
                    className="text-zinc-400 hover:text-sky-300 disabled:opacity-50"
                    disabled={!canStart}
                    title={blockedReason || '저장된 분석 결과로 클립만 다시 만듭니다(설정의 클립 구간·필터를 바꾼 뒤)'}
                    onClick={() => onAnalyze({ rebuild: true })}
                  >
                    클립 다시 만들기
                  </button>
                  <button
                    type="button"
                    className="text-zinc-400 hover:text-sky-300 disabled:opacity-50"
                    disabled={!canStart}
                    title={blockedReason || '판독까지 처음부터 다시 분석합니다'}
                    onClick={() => onAnalyze({ force: true })}
                  >
                    다시 분석
                  </button>
                </>
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
              {clipCount > 0 && (
                <button type="button" className="text-zinc-400 hover:text-rose-400" onClick={onTrashClips}>
                  전체 삭제
                </button>
              )}
            </>
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
          {visibleClipCount === 0 && (
            <p className="px-1 text-center text-sm text-zinc-500">
              {vod?.status === 'done' ? '조건에 맞는 클립이 없습니다' : '아직 클립이 없습니다. 분석을 시작하면 게임별로 만들어집니다.'}
            </p>
          )}
          {children}
        </div>
      )}
    </section>
  )
}
