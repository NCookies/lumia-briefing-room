import { useCallback, useEffect, useMemo, useState } from 'react'
import { cleanupReasonLabel, cleanupReasonTooltip } from '../cleanupPreview'
import { dayAnchorId, dayId, shortcutDays } from '../dayFold'
import { groupByDay } from '../gameDays'
import { gameHeadline, matchTypeLabel, type GameSummary } from '../games'
import { gameAssetUrl, getGames, setGamePinned } from '../gamesApi'
import { formatAgo } from '../grouping'
import { formatBytes } from '../retention'
import { useCleanupPreview } from '../useCleanupPreview'
import { useDayFold } from '../useDayFold'
import { DayShortcutBar } from './DayShortcutBar'
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

interface Props {
  active: boolean
  refreshTick: number
  onBackfill: () => void
  backfillLabel: string
}

export function GameList({ active, refreshTick, onBackfill, backfillLabel }: Props) {
  const [games, setGames] = useState<GameSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const cleanup = useCleanupPreview(active)
  const dayGroups = useMemo(
    () => groupByDay((games ?? []).map((g) => ({ ...g, matchStartUtc: g.matchStartUtc ?? '' }))),
    [games],
  )
  const dayList = useMemo(() => dayGroups.map((d) => d.day), [dayGroups])
  const fold = useDayFold('steam', dayList)

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
        {games.length > 0 && (
          <>
            <button
              type="button"
              className="rounded border border-zinc-600 px-2 py-0.5 text-xs hover:bg-zinc-700 disabled:opacity-40"
              disabled={fold.collapsed.size === 0}
              onClick={fold.expandAll}
            >
              모두 펼치기
            </button>
            <button
              type="button"
              className="rounded border border-zinc-600 px-2 py-0.5 text-xs hover:bg-zinc-700 disabled:opacity-40"
              disabled={fold.allCollapsed}
              onClick={fold.collapseAll}
            >
              모두 접기
            </button>
          </>
        )}
        <button
          type="button"
          className="ml-auto rounded border border-zinc-600 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-700"
          title="게임 로그에 남지 않은 과거 녹화에서 게임을 찾아 만듭니다"
          onClick={onBackfill}
        >
          {backfillLabel}
        </button>
      </div>
      {games.length === 0 && (
        <p className="text-sm text-zinc-500">
          아직 저장된 게임이 없습니다. 게임을 한 판 마치면 전체 영상과 교전 후보가 여기에 쌓입니다.
        </p>
      )}
      <DayShortcutBar shortcuts={shortcutDays(dayList, 'steam')} onGo={fold.go} />
      {dayGroups.map((dayGroup) => (
        <section
          key={dayGroup.day ?? 'unknown'}
          id={dayAnchorId('steam', dayGroup.day)}
          className="flex flex-col gap-2 [&+&]:mt-4"
        >
          <GameDayHeader
            day={dayGroup.day}
            gameCount={dayGroup.games.length}
            clipCount={dayGroup.games.reduce((n, g) => n + g.savedClipCount, 0)}
            clipBytes={dayGroup.games.reduce((n, g) => n + (g.fullVideoSizeBytes ?? 0), 0)}
            bytesLabel="풀영상 "
            collapsed={fold.collapsed.has(dayId(dayGroup.day))}
            onToggle={() => fold.toggle(dayGroup.day)}
          />
          {!fold.collapsed.has(dayId(dayGroup.day)) && (
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
                    {g.legacy && !g.hasFullVideo ? (
                      <span
                        className="rounded bg-amber-500/20 px-1.5 text-xs text-amber-200"
                        title={g.fullVideoError ?? undefined}
                      >
                        풀영상 없음(이전 버전)
                      </span>
                    ) : (
                      g.fullVideoError && <span className="text-xs text-amber-300">{g.fullVideoError}</span>
                    )}
                    <span className="text-xs text-zinc-300">저장한 클립 {g.savedClipCount}개</span>
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
          )}
        </section>
      ))}
      {error && <p className="text-sm text-rose-300">{error}</p>}
    </div>
  )
}
