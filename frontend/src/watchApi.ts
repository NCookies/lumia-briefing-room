export interface WatchFailure {
  key: string
  matchStartUtc: string
  message: string
  diskFull: boolean
  occurredAt: string
}

export async function getWatchFailures(): Promise<WatchFailure[]> {
  const res = await fetch('/api/watch/failures')
  if (!res.ok) throw new Error(`감시 실패 내역을 불러오지 못했습니다 (${res.status})`)
  return (await res.json()).failures as WatchFailure[]
}

export async function retryWatchFailure(key: string): Promise<void> {
  const res = await fetch(`/api/watch/failures/${encodeURIComponent(key)}/retry`, { method: 'POST' })
  if (!res.ok) throw new Error(`다시 시도를 요청하지 못했습니다 (${res.status})`)
}
