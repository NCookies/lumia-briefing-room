import { queueLabel } from './reanalyze.ts'
import type { Clip } from './types'

export interface RebuildStatus {
  state: 'idle' | 'queued' | 'running' | 'done' | 'error'
  message: string
  fraction: number
  /** 대기 중일 때만: 1 = 다음 차례. */
  position?: number | null
}

/** 이전 버전에서 분석해 풀영상이 없는 게임 - 저장된 클립으로 보여 준다. */
export function isLegacyWithoutVideo(game: { legacy?: boolean; hasFullVideo: boolean }): boolean {
  return game.legacy === true && !game.hasFullVideo
}

/** 클립 목록에서 이 게임의 클립만 일어난 순서로. */
export function clipsOfGame<T extends Pick<Clip, 'id' | 'matchStartUtc' | 'sessionDir' | 'videoOffsetSec'>>(
  clips: T[],
  game: { matchStartUtc: string | null; sessionDir?: string | null },
): T[] {
  if (!game.matchStartUtc) return []
  const start = Date.parse(game.matchStartUtc)
  return clips
    .filter((c) => c.matchStartUtc && Date.parse(c.matchStartUtc) === start && (c.sessionDir ?? null) === (game.sessionDir ?? null))
    .sort((a, b) => a.videoOffsetSec - b.videoOffsetSec)
}

export function rebuildStatusText(status: RebuildStatus): string | null {
  if (status.state === 'queued') return queueLabel(status.position)
  if (status.state === 'running') return `풀영상을 만드는 중… ${Math.round(status.fraction * 100)}%`
  if (status.state === 'done') return '풀영상을 만들었습니다'
  if (status.state === 'error') return status.message || '풀영상을 만들지 못했습니다'
  return null
}
