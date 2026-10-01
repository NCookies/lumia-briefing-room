import { cleanupReasonLabel, cleanupReasonTooltip, preserveLabel, type CleanupPreviewEntry } from '../cleanupPreview'
import { clipCountsLabel, gameHeadline, matchTypeLabel, recordingStopLabel, type GameSummary } from '../games'
import { gameAssetUrl } from '../gamesApi'
import { formatBytes } from '../retention'
import { GameMenu, type GameMenuItem } from './GameMenu'
import { GameTitle } from './GameTitle'

export interface RowTime {
  main: string
  sub?: string
}

function barColor(g: GameSummary): string {
  const p = g.matchResult?.placement
  if (p === 1 || g.matchResult?.outcome === '승리') return 'bg-emerald-500'
  if (p != null && p <= 3) return 'bg-sky-500'
  return 'bg-zinc-500'
}

interface Props {
  game: GameSummary
  time: RowTime
  due?: CleanupPreviewEntry
  onOpen: () => void
  onPin: () => void
  rebuild?: { label: string; disabled: boolean; onClick: () => void }
  /** 분석 대기열에 있는 게임: 대기 중(N번째)·진행 중 문구. 대기 중일 때만 취소할 수 있다. */
  job?: { text: string; queued: boolean; onCancel: () => void }
  menu?: GameMenuItem[]
  onRename?: (title: string | null) => void
}

/** 게임 목록의 게임 한 줄. 스팀 녹화 탭과 영상 파일 탭이 같이 쓴다(시간 칸만 다르다). */
export function GameRow({ game: g, time, due, onOpen, onPin, rebuild, job, menu, onRename }: Props) {
  return (
    <li
      className="flex cursor-pointer items-stretch overflow-hidden rounded border border-zinc-700 bg-zinc-800/60 hover:border-zinc-500 hover:bg-zinc-800"
      onClick={onOpen}
    >
      <div className={`w-1.5 shrink-0 ${barColor(g)}`} />
      <div className="flex flex-1 flex-wrap items-center gap-x-8 gap-y-2 px-4 py-3">
        <div className="w-20">
          <div
            className={`text-xl font-bold ${g.matchResult?.placement === 1 || g.matchResult?.outcome === '승리' ? 'text-emerald-400' : 'text-zinc-200'}`}
          >
            {gameHeadline(g.matchResult, g.recordingStopped)}
          </div>
          <div className="text-sm font-semibold text-zinc-300">
            {g.gameMode === 'cobalt' ? '코발트' : matchTypeLabel(g.matchResult)}
          </div>
        </div>
        <div className="w-32 text-sm">
          <div className="text-zinc-200">{time.main}</div>
          <div className="text-xs text-zinc-500">{time.sub ?? ''}</div>
        </div>
        <div className="w-28">
          {g.matchResult?.kills != null && (
            <>
              <div className="text-base font-bold text-zinc-100">
                {g.matchResult.tk ?? '-'} / {g.matchResult.kills} / {g.matchResult.assists ?? '-'}
              </div>
              <div className="text-xs text-zinc-500">TK / K / A</div>
            </>
          )}
        </div>
        <div className="flex min-w-[15.5rem] items-center gap-1">
          {(['me', 'teammate1', 'teammate2'] as const).map((slot) =>
            g.portraits[slot] ? (
              <div key={slot} className="aspect-[157/77] h-10 shrink-0 overflow-hidden rounded-lg border border-zinc-700">
                <img
                  className={`h-full w-full object-cover ${slot === 'me' ? 'origin-right scale-[1.08]' : ''}`}
                  src={gameAssetUrl(g.key, g.portraits[slot]!)}
                  alt=""
                />
              </div>
            ) : null,
          )}
        </div>
        {onRename ? (
          <GameTitle value={g.title} onSave={onRename} />
        ) : (
          g.title && <span className="max-w-xs truncate text-sm font-semibold text-zinc-100">{g.title}</span>
        )}
      </div>
      <div className="flex flex-wrap items-center justify-end gap-3 py-3 pr-4">
        {g.unsavedEditCount > 0 && (
          <span
            className="rounded bg-red-600 px-2 py-0.5 text-xs font-semibold text-white"
            title="보관한 클립의 범위를 고쳤지만 아직 클립에 반영하지 않았습니다. 열어서 저장하세요(다시 저장)."
          >
            {g.unsavedEditCount}개 저장 대기
          </span>
        )}
        {g.pinned && <span className="rounded bg-sky-600/30 px-1.5 text-xs text-sky-200" title="자동 정리에서 제외됩니다">
            고정
          </span>}
        {due && g.hasFullVideo && (
          <span className="rounded bg-rose-600/30 px-1.5 text-xs text-rose-200" title={cleanupReasonTooltip(due)}>
            {cleanupReasonLabel(due)}
            {preserveLabel(due) && <span className="ml-1 text-rose-100/80">· {preserveLabel(due)}</span>}
          </span>
        )}
        {recordingStopLabel(g.recordingStopped) ? (
          <span className="rounded bg-rose-600/25 px-1.5 text-xs text-rose-200" title={g.fullVideoError ?? undefined}>
            {recordingStopLabel(g.recordingStopped)}
          </span>
        ) : g.legacy && !g.hasFullVideo ? (
          <span className="rounded bg-amber-500/20 px-1.5 text-xs text-amber-200" title={g.fullVideoError ?? undefined}>
            풀영상 없음(이전 버전)
          </span>
        ) : (
          g.fullVideoError && <span className="text-xs text-amber-300">{g.fullVideoError}</span>
        )}
        {job && (
          <span className="flex items-center gap-1.5" data-testid="game-job">
            <span className="rounded bg-sky-500/20 px-1.5 text-xs text-sky-200">{job.text}</span>
            {job.queued && (
              <button
                type="button"
                className="text-xs text-amber-300 hover:underline"
                onClick={(e) => {
                  e.stopPropagation()
                  job.onCancel()
                }}
              >
                대기 취소
              </button>
            )}
          </span>
        )}
        {rebuild && !job && (
          <button
            type="button"
            className="rounded border border-sky-400 px-2 py-1 text-xs text-sky-100 hover:bg-sky-700/40 disabled:opacity-40"
            title="원본 녹화가 남아 있어 풀영상을 새로 만들 수 있습니다. 보관한 클립은 그대로 둡니다."
            disabled={rebuild.disabled}
            onClick={(e) => {
              e.stopPropagation()
              rebuild.onClick()
            }}
          >
            {rebuild.label}
          </button>
        )}
        <span className="text-xs text-zinc-300" title="후보: 앱이 찾은 교전 후보(삭제한 것 제외) · 보관: 클립으로 만든 것(자동 보관 포함)">
          {clipCountsLabel(g)}
        </span>
        <span className="text-xs text-zinc-500">
          {g.legacy && !g.hasFullVideo
            ? ''
            : g.hasFullVideo
              ? `풀영상 ${g.fullVideoSizeBytes != null ? formatBytes(g.fullVideoSizeBytes) : ''}`
              : g.fullVideoDeletedAt
                ? '풀영상 삭제됨'
                : '풀영상 없음'}
        </span>
        <span className="flex gap-2">
          <button
            type="button"
            className="rounded border border-zinc-600 px-2 py-1 text-xs hover:bg-zinc-700"
            title={g.pinned ? undefined : '자동 정리에서 제외됩니다'}
            onClick={(e) => {
              e.stopPropagation()
              onPin()
            }}
          >
            {g.pinned ? '고정 해제' : '고정'}
          </button>
          {menu && menu.length > 0 && <GameMenu items={menu} />}
        </span>
      </div>
    </li>
  )
}
