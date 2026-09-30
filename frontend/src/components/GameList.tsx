import { useCallback, useEffect, useState } from 'react'
import { cleanupReasonLabel, cleanupReasonTooltip } from '../cleanupPreview'
import { groupByDay } from '../gameDays'
import { gameHeadline, matchTypeLabel, type GameSummary } from '../games'
import { gameAssetUrl, getGames, setGamePinned } from '../gamesApi'
import { formatAgo } from '../grouping'
import { formatBytes } from '../retention'
import { useCleanupPreview } from '../useCleanupPreview'
import { GameDayHeader } from './GameDayHeader'
import { GameViewer } from './GameViewer'

function formatShort(iso: string | null): string {
  if (!iso) return '시각 미상'
  const d = new Date(iso)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${d.getMonth() + 1}/${d.getDate()} ${hh}:${mm}`
}

function barColor(g: GameSummary): string {
  const p = g.matchResult?.placement
  if (p === 1 || g.matchResult?.outcome === '승리') return 'bg-emerald-500'
  if (p != null && p <= 3) return 'bg-sky-500'
  return 'bg-zinc-500'
}

export function GameList({ active, refreshTick }: { active: boolean; refreshTick: number }) {
  const [games, setGames] = useState<GameSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const cleanup = useCleanupPreview(active)

  const load = useCallback(() => {
    getGames()
      .then(setGames)
      .catch((e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    if (active) load()
  }, [active, load, refreshTick])

  if (open) {
    return <GameViewer gameKey={open} onBack={() => setOpen(null)} onChanged={load} />
  }

  if (!games) return <p className="p-4 text-sm text-zinc-400">{error ?? '불러오는 중…'}</p>

  const total = games.reduce((sum, g) => sum + (g.fullVideoSizeBytes ?? 0), 0)

  return (
    <div className="flex flex-1 flex-col gap-2 p-4">
      <div className="flex items-baseline gap-3 text-sm text-zinc-300">
        <span>게임 {games.length}개</span>
        <span className="text-xs text-zinc-500">풀영상 {formatBytes(total)}</span>
      </div>
      {games.length === 0 && (
        <p className="text-sm text-zinc-500">
          아직 저장된 게임이 없습니다. 게임을 한 판 마치면 전체 영상과 교전 후보가 여기에 쌓입니다.
        </p>
      )}
      {groupByDay(games.map((g) => ({ ...g, matchStartUtc: g.matchStartUtc ?? '' }))).map((dayGroup) => (
        <section key={dayGroup.day ?? 'unknown'} className="flex flex-col gap-2 [&+&]:mt-4">
          <GameDayHeader
            day={dayGroup.day}
            gameCount={dayGroup.games.length}
            clipCount={dayGroup.games.reduce((n, g) => n + g.savedClipCount, 0)}
            clipBytes={dayGroup.games.reduce((n, g) => n + (g.fullVideoSizeBytes ?? 0), 0)}
            bytesLabel="풀영상 "
          />
          <ul className="flex flex-col gap-2">
            {dayGroup.games.map((g) => {
              const due = cleanup[g.key]
              return (
                <li
                  key={g.key}
                  className="flex cursor-pointer items-stretch overflow-hidden rounded border border-zinc-700 bg-zinc-800/60 hover:border-zinc-500 hover:bg-zinc-800"
                  onClick={() => setOpen(g.key)}
                >
                  <div className={`w-1.5 shrink-0 ${barColor(g)}`} />
                  <div className="flex flex-1 flex-wrap items-center gap-x-8 gap-y-2 px-4 py-3">
                    <div className="w-20">
                      <div
                        className={`text-xl font-bold ${g.matchResult?.placement === 1 || g.matchResult?.outcome === '승리' ? 'text-emerald-400' : 'text-zinc-200'}`}
                      >
                        {gameHeadline(g.matchResult)}
                      </div>
                      <div className="text-sm font-semibold text-zinc-300">
                        {g.gameMode === 'cobalt' ? '코발트' : matchTypeLabel(g.matchResult)}
                      </div>
                    </div>
                    <div className="w-32 text-sm">
                      <div className="text-zinc-200">{formatShort(g.matchStartUtc)}</div>
                      <div className="text-xs text-zinc-500">{g.matchStartUtc ? formatAgo(g.matchStartUtc) : ''}</div>
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
                    <div className="flex min-w-[7.5rem] items-center gap-1">
                      {(['me', 'teammate1', 'teammate2'] as const).map((slot) =>
                        g.portraits[slot] ? (
                          <img
                            key={slot}
                            className="h-10 w-10 rounded-full object-cover"
                            src={gameAssetUrl(g.key, g.portraits[slot]!)}
                            alt=""
                          />
                        ) : null,
                      )}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center justify-end gap-3 py-3 pr-4">
                    {g.unsavedEditCount > 0 && (
                      <span
                        className="rounded bg-red-600 px-2 py-0.5 text-xs font-semibold text-white"
                        title="범위를 고쳤지만 아직 클립에 반영하지 않은 후보입니다. 열어서 저장하세요."
                      >
                        편집 {g.unsavedEditCount}개 저장 안 됨
                      </span>
                    )}
                    {g.pinned && <span className="rounded bg-sky-600/30 px-1.5 text-xs text-sky-200">고정</span>}
                    {due && g.hasFullVideo && (
                      <span className="rounded bg-rose-600/30 px-1.5 text-xs text-rose-200" title={cleanupReasonTooltip(due)}>
                        {cleanupReasonLabel(due)}
                      </span>
                    )}
                    {g.fullVideoError && <span className="text-xs text-amber-300">{g.fullVideoError}</span>}
                    <span className="text-xs text-zinc-300">저장한 클립 {g.savedClipCount}개</span>
                    <span className="text-xs text-zinc-500">
                      {g.hasFullVideo
                        ? `풀영상 ${g.fullVideoSizeBytes != null ? formatBytes(g.fullVideoSizeBytes) : ''}`
                        : g.fullVideoDeletedAt
                          ? '풀영상 삭제됨'
                          : '풀영상 없음'}
                    </span>
                    <span className="flex gap-2">
                      <button
                        type="button"
                        className="rounded border border-zinc-600 px-2 py-1 text-xs hover:bg-zinc-700"
                        onClick={(e) => {
                          e.stopPropagation()
                          void setGamePinned(g.key, !g.pinned)
                            .then(load)
                            .catch((err: Error) => setError(err.message))
                        }}
                      >
                        {g.pinned ? '고정 해제' : '고정'}
                      </button>
                    </span>
                  </div>
                </li>
              )
            })}
          </ul>
        </section>
      ))}
      {error && <p className="text-sm text-rose-300">{error}</p>}
    </div>
  )
}
