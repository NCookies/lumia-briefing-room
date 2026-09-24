import type { BackfillPreview, BackfillStatus } from './backfill'

const BASE = '/api/backfill'

async function json<T>(res: Response, action: string): Promise<T> {
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

export async function getBackfillPreview(): Promise<BackfillPreview> {
  return json(await fetch(`${BASE}/preview`), '분석 대상 조회')
}

export async function getBackfillStatus(): Promise<BackfillStatus> {
  return json(await fetch(BASE), '분석 상태 조회')
}

export async function startBackfill(): Promise<void> {
  await json(await fetch(`${BASE}/start`, { method: 'POST' }), '분석 시작')
}

export async function cancelBackfill(): Promise<BackfillStatus> {
  return json(await fetch(`${BASE}/cancel`, { method: 'POST' }), '분석 취소')
}
