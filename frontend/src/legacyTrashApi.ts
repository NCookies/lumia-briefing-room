const BASE = '/api'

async function jsonOrThrow<T>(res: Response, action: string): Promise<T> {
  if (!res.ok) throw new Error(`${action}에 실패했습니다 (${res.status})`)
  return res.json()
}

export async function getLegacyTrashCount(): Promise<number> {
  const body = await jsonOrThrow<{ count: number }>(await fetch(`${BASE}/legacy-trash`), '이전 휴지통 확인')
  return body.count
}

export async function migrateLegacyTrash(action: 'restore' | 'recycle'): Promise<number> {
  const res = await fetch(`${BASE}/legacy-trash/migrate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action }),
  })
  const body = await jsonOrThrow<{ migrated: number }>(res, '이전 휴지통 처리')
  return body.migrated
}
