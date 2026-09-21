import type { Clip, UserLabel } from './types'

const BASE = '/api'

export interface ClipQuery {
  tags?: string[]
  dayNight?: string
  gameMode?: string
  pinned?: boolean
  trashed?: boolean
  minPvpScore?: number
  label?: string
  sort?: string
}

async function checkOk(res: Response, action: string): Promise<Response> {
  if (!res.ok) {
    throw new Error(`${action}에 실패했습니다 (${res.status})`)
  }
  return res
}

export async function listClips(query: ClipQuery = {}): Promise<Clip[]> {
  const params = new URLSearchParams()
  if (query.tags?.length) params.set('tags', query.tags.join(','))
  if (query.dayNight) params.set('dayNight', query.dayNight)
  if (query.gameMode) params.set('gameMode', query.gameMode)
  if (query.pinned) params.set('pinned', 'true')
  if (query.trashed) params.set('trashed', 'true')
  if (query.minPvpScore) params.set('minPvpScore', String(query.minPvpScore))
  if (query.label) params.set('label', query.label)
  if (query.sort) params.set('sort', query.sort)

  const res = await checkOk(await fetch(`${BASE}/clips?${params}`), '클립 목록 조회')
  const clips: Clip[] = await res.json()
  return clips.map((c) => ({ ...c, userLabel: c.userLabel ?? null }))
}

export async function patchClip(
  id: string,
  body: Partial<Pick<Clip, 'title' | 'pinned'>> & { userLabel?: UserLabel },
): Promise<Clip> {
  const res = await checkOk(
    await fetch(`${BASE}/clips/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
    '클립 수정',
  )
  return res.json()
}

export async function trashClip(id: string): Promise<void> {
  await checkOk(await fetch(`${BASE}/clips/${id}/trash`, { method: 'POST' }), '삭제')
}

export async function restoreClip(id: string): Promise<void> {
  await checkOk(await fetch(`${BASE}/clips/${id}/restore`, { method: 'POST' }), '복구')
}

export async function deleteClipForever(id: string): Promise<void> {
  await checkOk(await fetch(`${BASE}/clips/${id}`, { method: 'DELETE' }), '영구 삭제')
}

export function videoUrl(id: string, version?: number): string {
  return `${BASE}/clips/${id}/video${version === undefined ? '' : `?v=${version}`}`
}

export async function emptyTrash(): Promise<{ deleted: number; bytes: number }> {
  const res = await checkOk(await fetch(`${BASE}/trash/empty`, { method: 'POST' }), '휴지통 비우기')
  return res.json()
}

export function resultImageUrl(id: string): string {
  return `${BASE}/clips/${id}/result-image`
}

export function thumbnailUrl(id: string, version?: number): string {
  return `${BASE}/clips/${id}/thumbnail${version === undefined ? '' : `?v=${version}`}`
}

export async function trimClip(id: string, start: number, end: number): Promise<Clip> {
  const res = await fetch(`${BASE}/clips/${id}/trim`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ start, end }),
  })
  if (!res.ok) {
    let detail = ''
    try {
      detail = (await res.json()).detail ?? ''
    } catch {
      // 본문이 JSON 이 아니면 상태 코드만 보여준다
    }
    throw new Error(`자르기에 실패했습니다 (${res.status})${detail ? `: ${detail}` : ''}`)
  }
  return res.json()
}
