import { useEffect, useState } from 'react'
import { getRetention } from './exportApi'
import { getGames } from './gamesApi'

export interface StorageTotals {
  totalBytes: number
  steamBytes: number
  vodBytes: number
  limitGb: number | null
  autoCleanEnabled: boolean
}

const CACHE_KEY = 'storageUsageTotals'
let last: StorageTotals | null = null

function readCache(): StorageTotals | null {
  if (last) return last
  try {
    const parsed = JSON.parse(localStorage.getItem(CACHE_KEY) ?? 'null')
    if (parsed && typeof parsed.totalBytes === 'number' && typeof parsed.steamBytes === 'number') last = parsed
  } catch {
    // 저장소를 못 읽어도 막대는 서버 응답으로 채운다
  }
  return last
}

function writeCache(totals: StorageTotals) {
  last = totals
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(totals))
  } catch {
    // 저장하지 못해도 화면은 그대로 쓴다
  }
}

/** 풀영상 합계(스팀 녹화 + 영상 파일)와 자동 정리 한도. 마지막 값을 기억해 두었다가 먼저 보이고, `version` 이 바뀌면(게임 목록이 다시 읽히면) 다시 읽는다. */
export function useStorageUsage(active: boolean, version: unknown): StorageTotals | null {
  const [totals, setTotals] = useState<StorageTotals | null>(readCache)

  useEffect(() => {
    if (!active) return
    let cancelled = false
    Promise.all([getGames('all'), getRetention()])
      .then(([games, retention]) => {
        if (cancelled) return
        const bytesOf = (source: 'steam' | 'vod') =>
          games.filter((g) => (g.source ?? 'steam') === source).reduce((sum, g) => sum + (g.fullVideoSizeBytes ?? 0), 0)
        const next: StorageTotals = {
          totalBytes: games.reduce((sum, g) => sum + (g.fullVideoSizeBytes ?? 0), 0),
          steamBytes: bytesOf('steam'),
          vodBytes: bytesOf('vod'),
          limitGb: retention.maxTotalGb,
          autoCleanEnabled: retention.autoCleanEnabled,
        }
        writeCache(next)
        setTotals(next)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [active, version])

  return totals
}
