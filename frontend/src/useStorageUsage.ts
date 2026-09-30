import { useEffect, useState } from 'react'
import { getRetention } from './exportApi'
import { getGames } from './gamesApi'

export interface StorageTotals {
  totalBytes: number
  limitGb: number | null
  autoCleanEnabled: boolean
}

/** 풀영상 합계(스팀 녹화 + 영상 파일)와 자동 정리 한도. `version` 이 바뀌면(게임 목록이 다시 읽히면) 다시 읽는다. */
export function useStorageUsage(active: boolean, version: unknown): StorageTotals | null {
  const [totals, setTotals] = useState<StorageTotals | null>(null)

  useEffect(() => {
    if (!active) return
    let cancelled = false
    Promise.all([getGames('all'), getRetention()])
      .then(([games, retention]) => {
        if (cancelled) return
        setTotals({
          totalBytes: games.reduce((sum, g) => sum + (g.fullVideoSizeBytes ?? 0), 0),
          limitGb: retention.maxTotalGb,
          autoCleanEnabled: retention.autoCleanEnabled,
        })
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [active, version])

  return totals
}
