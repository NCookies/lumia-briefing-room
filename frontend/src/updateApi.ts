import type { CheckResult, UpdateStatus } from './update'

const BASE = '/api/update'

async function jsonOrThrow<T>(res: Response, action: string): Promise<T> {
  if (!res.ok) throw new Error(`${action}에 실패했습니다 (${res.status})`)
  return res.json()
}

export const getUpdateStatus = async (): Promise<UpdateStatus> =>
  jsonOrThrow(await fetch(`${BASE}/status`), '업데이트 상태 불러오기')

export const checkForUpdate = async (): Promise<CheckResult> =>
  jsonOrThrow(await fetch(`${BASE}/check`, { method: 'POST' }), '업데이트 확인')

export const ackUpdate = async (): Promise<void> => {
  await fetch(`${BASE}/ack`, { method: 'POST' })
}

export const startUpdateInstall = async (): Promise<UpdateStatus> =>
  jsonOrThrow(await fetch(`${BASE}/install`, { method: 'POST' }), '업데이트 시작')
