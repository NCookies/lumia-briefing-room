import { useEffect, useRef, useState } from 'react'
import { listClips, thumbnailUrl } from '../api'
import { formatClock, type GameDetail } from '../games'
import { getRebuildStatus, startRebuildFullVideo } from '../gamesApi'
import { clipsOfGame, rebuildStatusText, type RebuildStatus } from '../legacyGame'
import { clipsOfVodGame, type SavedClipRef } from '../vodGames'
import { loadVolume, saveVolume } from '../volume'
import { ClipVideo } from './ClipVideo'

const POLL_MS = 1500

/** 이전 버전에서 분석해 풀영상이 없는 게임: 안내 + 예전 방식으로 저장된 클립 목록·재생. 원본이 남았으면 풀영상 만들기. */
export function LegacyGamePanel({ game, onRebuilt }: { game: GameDetail; onRebuilt: () => void }) {
  const [clips, setClips] = useState<SavedClipRef[] | null>(null)
  const [playingId, setPlayingId] = useState<string | null>(null)
  const [rebuild, setRebuild] = useState<RebuildStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const volume = useRef(loadVolume())

  useEffect(() => {
    if (game.source === 'vod') {
      const mine = clipsOfVodGame(game)
      setClips(mine)
      setPlayingId((id) => id ?? mine[0]?.id ?? null)
      return
    }
    listClips()
      .then((all) => {
        const mine: SavedClipRef[] = clipsOfGame(all, game).map((c) => ({ id: c.id, title: c.title, durationSec: c.durationSec }))
        setClips(mine)
        setPlayingId((id) => id ?? mine[0]?.id ?? null)
      })
      .catch((e: Error) => setError(e.message))
  }, [game])

  const running = rebuild?.state === 'running'
  useEffect(() => {
    if (!running) return
    const timer = window.setInterval(() => {
      getRebuildStatus(game.gameKey)
        .then((next) => {
          setRebuild(next)
          if (next.state === 'done') onRebuilt()
        })
        .catch((e: Error) => setError(e.message))
    }, POLL_MS)
    return () => window.clearInterval(timer)
  }, [running, game.gameKey, onRebuilt])

  const start = () => {
    setError(null)
    startRebuildFullVideo(game.gameKey)
      .then(setRebuild)
      .catch((e: Error) => setError(e.message))
  }

  const playing = clips?.find((c) => c.id === playingId) ?? null
  const status = rebuild ? rebuildStatusText(rebuild) : null

  return (
    <div className="flex min-h-0 flex-1 gap-3" data-testid="legacy-panel">
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <p className="rounded border border-amber-500/60 bg-amber-500/10 p-3 text-sm text-amber-200">
          이전 버전에서 분석한 게임이라 풀영상이 없습니다. 저장된 클립으로 볼 수 있습니다.
        </p>
        {game.canRebuildFullVideo && (
          <div className="flex flex-wrap items-center gap-3 rounded border border-sky-500/50 bg-sky-500/10 p-3 text-sm text-sky-100">
            <span>원본이 남아 있습니다 — 풀영상을 만들면 이 게임도 새 게임처럼 볼 수 있습니다. 저장된 클립은 그대로 둡니다.</span>
            <button
              type="button"
              disabled={running}
              className="rounded border border-sky-400 px-3 py-1 hover:bg-sky-700/40 disabled:opacity-40"
              onClick={start}
            >
              풀영상 만들기
            </button>
          </div>
        )}
        {status && <p className={`text-sm ${rebuild?.state === 'error' ? 'text-rose-300' : 'text-emerald-300'}`}>{status}</p>}
        {error && <p className="text-sm text-rose-300">{error}</p>}
        {playing ? (
          <div className="flex flex-col gap-1">
            <ClipVideo
              key={playing.id}
              clipId={playing.id}
              nextClipId={null}
              version={playing.durationSec}
              videoRef={(el) => {
                if (!el) return
                el.volume = volume.current.volume
                el.muted = volume.current.muted
              }}
              onVolumeChange={(v) => {
                volume.current = { volume: v.volume, muted: v.muted }
                saveVolume(volume.current)
              }}
            />
            <span className="text-sm text-zinc-300">{playing.title}</span>
          </div>
        ) : (
          clips && <p className="text-sm text-zinc-500">이 게임의 저장된 클립이 없습니다(클립을 삭제했을 수 있습니다).</p>
        )}
      </div>
      <aside className="flex w-80 shrink-0 flex-col gap-2 overflow-y-auto">
        <h3 className="text-sm font-semibold text-zinc-200">저장된 클립 {clips ? clips.length : ''}개</h3>
        {!clips && <p className="text-sm text-zinc-400">불러오는 중…</p>}
        <ul className="flex flex-col gap-2">
          {clips?.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                className={`flex w-full items-center gap-2 rounded border p-1 text-left hover:border-zinc-400 ${c.id === playingId ? 'border-yellow-500 bg-zinc-800' : 'border-zinc-700'}`}
                onClick={() => setPlayingId(c.id)}
              >
                <img className="h-12 w-20 shrink-0 rounded object-cover" src={thumbnailUrl(c.id, c.durationSec)} alt="" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-zinc-100">{c.title}</span>
                  <span className="text-xs text-zinc-500">{formatClock(c.durationSec)}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  )
}
