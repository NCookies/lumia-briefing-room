import { useEffect, useRef, useState } from 'react'
import { ACTIVITY_POLL_MS, REFRESH_INTERVAL_MS, shouldRefresh, type ActivityTask } from './activity'
import { getActivity } from './activityApi'

/** 백그라운드 작업 목록과, 작업 중이거나 막 끝났을 때 목록을 다시 읽으라는 신호(refreshTick). */
export function useActivity(externalBusy: boolean) {
  const [tasks, setTasks] = useState<ActivityTask[]>([])
  const [refreshTick, setRefreshTick] = useState(0)
  const wasBusy = useRef(false)
  const lastRefresh = useRef(Date.now())
  const externalBusyRef = useRef(externalBusy)
  externalBusyRef.current = externalBusy

  useEffect(() => {
    let cancelled = false
    const poll = async () => {
      let current: ActivityTask[] = []
      try {
        current = await getActivity()
      } catch {
        // 서버가 잠깐 응답하지 못해도 화면은 그대로 둔다
        return
      }
      if (cancelled) return
      setTasks(current)
      const busy = current.length > 0 || externalBusyRef.current
      const now = Date.now()
      if (shouldRefresh({ wasBusy: wasBusy.current, busy, msSinceRefresh: now - lastRefresh.current, intervalMs: REFRESH_INTERVAL_MS })) {
        lastRefresh.current = now
        setRefreshTick((t) => t + 1)
      }
      wasBusy.current = busy
    }
    void poll()
    const timer = window.setInterval(poll, ACTIVITY_POLL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  return { tasks, refreshTick }
}
