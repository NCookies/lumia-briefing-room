import type { Clip, GameRecord, UserLabel } from './types'

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
  source?: 'steam' | 'vod'
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
  if (query.source) params.set('source', query.source)

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

export async function emptyTrash(source: 'steam' | 'vod' = 'steam'): Promise<{ deleted: number; bytes: number }> {
  const res = await checkOk(await fetch(`${BASE}/trash/empty?source=${source}`, { method: 'POST' }), '휴지통 비우기')
  return res.json()
}

export interface ReprocessStatus {
  state: 'running' | 'done' | 'error'
  message: string
  clips: number
}

export async function startReprocess(clipId: string): Promise<string> {
  const res = await fetch(`${BASE}/games/reprocess`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ clipId }),
  })
  if (!res.ok) {
    let detail = ''
    try {
      detail = (await res.json()).detail ?? ''
    } catch {
      // 본문이 JSON 이 아니면 상태 코드만 보여준다
    }
    throw new Error(detail || `다시 분석을 시작하지 못했습니다 (${res.status})`)
  }
  return (await res.json()).key
}

export async function getReprocessStatus(key: string): Promise<ReprocessStatus> {
  const res = await checkOk(await fetch(`${BASE}/games/reprocess/${key}`), '분석 상태 조회')
  return res.json()
}

export async function listGameRecords(): Promise<GameRecord[]> {
  const res = await checkOk(await fetch(`${BASE}/games/records`), '게임 기록 조회')
  return res.json()
}

export async function deleteGameRecord(id: string): Promise<void> {
  const res = await fetch(`${BASE}/games/records/${id}`, { method: 'DELETE' })
  if (!res.ok && res.status !== 404) throw new Error(`게임 기록 삭제에 실패했습니다 (${res.status})`)
}

export function gameRecordImageUrl(id: string): string {
  return `${BASE}/games/records/${id}/result-image`
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

export async function splitClip(id: string, ranges: { start: number; end: number }[]): Promise<Clip[]> {
  const res = await fetch(`${BASE}/clips/${id}/split`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ranges }),
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

export function proxyVideoUrl(id: string, version?: number): string {
  return `${BASE}/clips/${id}/video?proxy=1${version === undefined ? '' : `&v=${version}`}`
}

export interface ProxyStatus {
  state: 'none' | 'running' | 'ready' | 'failed'
  progress: number
  message?: string
}

export async function startProxy(id: string): Promise<ProxyStatus> {
  const res = await checkOk(await fetch(`${BASE}/clips/${id}/proxy`, { method: 'POST' }), '재생용 영상 만들기')
  return res.json()
}

export async function getProxyStatus(id: string): Promise<ProxyStatus> {
  const res = await checkOk(await fetch(`${BASE}/clips/${id}/proxy`), '재생용 영상 상태 조회')
  return res.json()
}
