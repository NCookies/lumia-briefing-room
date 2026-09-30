const BASE = '/api/storage'

export interface StorageInfo {
  layout: 'new' | 'legacy'
  root: string | null
  fullVideos: string | null
  suggestedRoot: string | null
  resolved: { clips: string; fullVideos: string; library: string; proxyCache: string }
  legacy: { clips: string; vodClips: string; games: string }
  freeGb: { clips: number | null; fullVideos: number | null }
  canUndo: boolean
}

interface MoveJob {
  state: 'idle' | 'running' | 'done' | 'error'
  doneBytes: number
  totalBytes: number
  moved: number
  message: string
}

async function jsonOrThrow<T>(res: Response, action: string): Promise<T> {
  if (!res.ok) {
    let detail = ''
    try {
      detail = (await res.json()).detail ?? ''
    } catch {
      // 본문이 JSON 이 아니면 상태 코드만 보여준다
    }
    throw new Error(`${action}에 실패했습니다 (${res.status})${detail ? `: ${detail}` : ''}`)
  }
  return res.json()
}

export async function getStorage(): Promise<StorageInfo> {
  return jsonOrThrow(await fetch(BASE), '저장 위치 불러오기')
}

const POLL_MS = 300

export async function migrateStorage(
  root: string,
  fullVideos: string | null,
  onProgress: (fraction: number) => void,
): Promise<{ moved: number }> {
  let job = await jsonOrThrow<MoveJob>(
    await fetch(`${BASE}/migrate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ root, fullVideos }),
    }),
    '저장 위치 바꾸기',
  )
  while (job.state === 'running') {
    onProgress(job.totalBytes > 0 ? job.doneBytes / job.totalBytes : 0)
    await new Promise((resolve) => setTimeout(resolve, POLL_MS))
    job = await jsonOrThrow<MoveJob>(await fetch(`${BASE}/migrate`), '진행 상황 확인')
  }
  if (job.state === 'error') throw new Error(job.message)
  onProgress(1)
  return { moved: job.moved }
}

export async function undoStorage(): Promise<boolean> {
  const body = await jsonOrThrow<{ restored: boolean }>(await fetch(`${BASE}/undo`, { method: 'POST' }), '되돌리기')
  return body.restored
}
