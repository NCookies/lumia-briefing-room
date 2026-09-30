import { useCallback, useEffect, useState } from 'react'
import { getRebuildStatus, startRebuildFullVideo } from './gamesApi'
import { rebuildStatusText } from './legacyGame'

const POLL_MS = 1500

export interface RebuildState {
  key: string | null
  text: string | null
  error: boolean
}

/** 게임 목록에서 옛 게임의 풀영상 만들기를 시작하고 끝날 때까지 진행률을 읽는다. 한 번에 한 게임만(서버도 하나씩 돈다). */
export function useRebuildFullVideo(onDone: () => void) {
  const [state, setState] = useState<RebuildState>({ key: null, text: null, error: false })
  const [running, setRunning] = useState<string | null>(null)

  useEffect(() => {
    if (!running) return
    const timer = window.setInterval(() => {
      getRebuildStatus(running)
        .then((next) => {
          setState({ key: running, text: rebuildStatusText(next), error: next.state === 'error' })
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

  const start = useCallback((key: string) => {
    setState({ key, text: '풀영상을 만드는 중… 0%', error: false })
    startRebuildFullVideo(key)
      .then(() => setRunning(key))
      .catch((e: Error) => setState({ key, text: e.message, error: true }))
  }, [])

  return { state, running, start }
}
