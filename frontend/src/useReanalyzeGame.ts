import { useCallback, useEffect, useState } from 'react'
import { getReanalyzePlan, getReanalyzeStatus, startReanalyze } from './gamesApi'
import { reanalyzeStatusText, type ReanalyzeMode } from './reanalyze'

const POLL_MS = 1500

export interface ReanalyzeState {
  key: string | null
  text: string | null
  error: boolean
}

/** 게임 행 `⋯` → `다시 분석`: 방식을 확인하고(확인 창은 호출하는 쪽) 끝날 때까지 진행률을 읽는다. 한 번에 한 게임만(서버도 하나씩 돈다). */
export function useReanalyzeGame(onDone: () => void) {
  const [state, setState] = useState<ReanalyzeState>({ key: null, text: null, error: false })
  const [running, setRunning] = useState<string | null>(null)

  useEffect(() => {
    if (!running) return
    const timer = window.setInterval(() => {
      getReanalyzeStatus(running)
        .then((next) => {
          setState({ key: running, text: reanalyzeStatusText(next), error: next.state === 'error' })
          if (next.state === 'running') return
          setRunning(null)
          onDone()
        })
        .catch((e: Error) => {
          setState({ key: running, text: e.message, error: true })
          setRunning(null)
        })
    }, POLL_MS)
    return () => window.clearInterval(timer)
  }, [running, onDone])

  const plan = useCallback((key: string): Promise<ReanalyzeMode | null> => getReanalyzePlan(key), [])

  const start = useCallback((key: string) => {
    setState({ key, text: '다시 분석을 시작하는 중…', error: false })
    startReanalyze(key)
      .then(() => setRunning(key))
      .catch((e: Error) => setState({ key, text: e.message, error: true }))
  }, [])

  const fail = useCallback((key: string, message: string) => setState({ key, text: message, error: true }), [])

  return { state, running, plan, start, fail }
}
