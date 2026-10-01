import { useCallback, useEffect, useRef, useState } from 'react'
import { cancelQueuedGameJob, getReanalyzePlan, getReanalyzeStatus, getRebuildStatus, startReanalyze, startRebuildFullVideo } from './gamesApi'
import { rebuildStatusText, type RebuildStatus } from './legacyGame'
import { reanalyzeStatusText, type ReanalyzeMode, type ReanalyzeStatus } from './reanalyze'

const POLL_MS = 1500

export type GameJobKind = 'reanalyze' | 'rebuild'
type Status = ReanalyzeStatus | RebuildStatus

export interface GameJob {
  kind: GameJobKind
  state: 'queued' | 'running'
  /** 행 배지에 쓰는 문구: "대기 중 (2번째)" / "다시 분석하는 중… 42%". */
  text: string
}

export interface GameJobResult {
  key: string
  text: string
  error: boolean
}

const fetchStatus = (kind: GameJobKind, key: string): Promise<Status> => (kind === 'reanalyze' ? getReanalyzeStatus(key) : getRebuildStatus(key))
const textOf = (kind: GameJobKind, status: Status): string | null =>
  kind === 'reanalyze' ? reanalyzeStatusText(status as ReanalyzeStatus) : rebuildStatusText(status as RebuildStatus)
const activeState = (status: Status): 'queued' | 'running' | null => (status.state === 'queued' || status.state === 'running' ? status.state : null)

/**
 * 스팀 녹화 탭 게임 행의 `다시 분석`·`풀영상 만들기`. 서버가 요청을 대기열에 받아 차례로 돌리므로 여러 게임을 연달아 눌러도 된다.
 * 게임마다 대기 중/진행 중을 읽고(`jobs`), 끝나거나 실패한 마지막 결과는 `result` 로 보여 준다.
 */
export function useGameJobs(onDone: () => void) {
  const [jobs, setJobs] = useState<Record<string, GameJob>>({})
  const [result, setResult] = useState<GameJobResult | null>(null)
  const jobsRef = useRef(jobs)
  jobsRef.current = jobs
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone
  const hasActive = Object.keys(jobs).length > 0

  const finish = useCallback((key: string, text: string | null, error: boolean) => {
    setJobs((prev) => Object.fromEntries(Object.entries(prev).filter(([k]) => k !== key)))
    if (text) setResult({ key, text, error })
  }, [])

  const update = useCallback((key: string, kind: GameJobKind, state: 'queued' | 'running', text: string | null) => {
    setJobs((prev) => ({ ...prev, [key]: { kind, state, text: text ?? '' } }))
  }, [])

  useEffect(() => {
    if (!hasActive) return
    const timer = window.setInterval(() => {
      Object.entries(jobsRef.current).forEach(([key, job]) => {
        fetchStatus(job.kind, key)
          .then((next) => {
            const state = activeState(next)
            if (state) return update(key, job.kind, state, textOf(job.kind, next))
            finish(key, next.state === 'idle' ? null : textOf(job.kind, next), next.state === 'error')
            onDoneRef.current()
          })
          .catch((e: Error) => finish(key, e.message, true))
      })
    }, POLL_MS)
    return () => window.clearInterval(timer)
  }, [hasActive, finish, update])

  const begin = useCallback(
    (kind: GameJobKind, key: string, request: Promise<Status>) => {
      setResult(null)
      update(key, kind, 'queued', '요청하는 중…')
      request
        .then((status) => update(key, kind, activeState(status) ?? 'queued', textOf(kind, status)))
        .catch((e: Error) => finish(key, e.message, true))
    },
    [finish, update],
  )

  const plan = useCallback((key: string): Promise<ReanalyzeMode | null> => getReanalyzePlan(key), [])
  const startReanalysis = useCallback((key: string) => begin('reanalyze', key, startReanalyze(key)), [begin])
  const startRebuild = useCallback((key: string) => begin('rebuild', key, startRebuildFullVideo(key)), [begin])
  const cancel = useCallback(
    (key: string) =>
      cancelQueuedGameJob(key)
        .then(() => finish(key, null, false))
        .catch((e: Error) => finish(key, e.message, true)),
    [finish],
  )
  const fail = useCallback((key: string, message: string) => setResult({ key, text: message, error: true }), [])

  return { jobs, result, plan, startReanalysis, startRebuild, cancel, fail }
}
