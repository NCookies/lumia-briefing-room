import type { RebuildStatus } from './legacyGame'
import type { Candidate, CandidateUser, GameDetail, GameSummary } from './games'

const BASE = '/api/games'

async function jsonOrThrow<T>(res: Response, action: string): Promise<T> {
  if (!res.ok) {
    let detail = ''
    try {
      detail = (await res.json()).detail ?? ''
    } catch {
      // 본문이 JSON 이 아니어도 상태 코드로 알린다
    }
    throw new Error(detail || `${action}에 실패했습니다 (${res.status})`)
  }
  return res.json()
}

export async function getGames(source: 'steam' | 'vod' | 'all' = 'steam'): Promise<GameSummary[]> {
  return (await jsonOrThrow<{ games: GameSummary[] }>(await fetch(`${BASE}?source=${source}`), '게임 목록 불러오기')).games
}

export async function getGame(key: string): Promise<GameDetail> {
  return jsonOrThrow(await fetch(`${BASE}/${key}`), '게임 불러오기')
}

export const gameVideoUrl = (key: string) => `${BASE}/${key}/video`
export const gameAssetUrl = (key: string, name: string) => `${BASE}/${key}/asset/${name}`

const send = (method: string, url: string, body?: unknown) =>
  fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

export async function setGamePinned(key: string, pinned: boolean): Promise<GameSummary> {
  return jsonOrThrow(await send('PATCH', `${BASE}/${key}`, { pinned }), '고정')
}

export type CandidatePatch = Partial<Pick<CandidateUser, 'start' | 'end' | 'dismissed' | 'title'>> & { label?: 'combat' | 'hunt' | null }

export async function patchCandidate(key: string, id: string, patch: CandidatePatch): Promise<Candidate> {
  return jsonOrThrow(await send('PATCH', `${BASE}/${key}/candidates/${id}`, patch), '후보 수정')
}

export async function addCandidate(key: string, start: number, end: number, title?: string): Promise<Candidate> {
  return jsonOrThrow(await send('POST', `${BASE}/${key}/candidates`, { start, end, title }), '구간 추가')
}

export async function deleteCandidate(key: string, id: string): Promise<void> {
  await jsonOrThrow(await send('DELETE', `${BASE}/${key}/candidates/${id}`), '구간 삭제')
}

export interface ArchiveResult {
  clipId: string
  category: string | null
}

/** 후보를 클립으로 만들어 카테고리에 보관한다(이미 보관했으면 고친 범위를 반영해 다시 저장). */
export async function saveCandidate(key: string, id: string, category?: string): Promise<ArchiveResult> {
  return jsonOrThrow(await send('POST', `${BASE}/${key}/candidates/${id}/save`, { category }), '보관')
}

export interface BatchResult {
  saved: { candidateId: string; clipId: string }[]
  failed: { candidateId: string; error: string }[]
}

export async function saveBatch(key: string, mode: 'all' | 'certain' | 'ids', ids?: string[], category?: string): Promise<BatchResult> {
  return jsonOrThrow(await send('POST', `${BASE}/${key}/save`, { mode, ids, category }), '일괄 보관')
}

export async function startRebuildFullVideo(key: string): Promise<RebuildStatus> {
  return jsonOrThrow(await send('POST', `${BASE}/${key}/full-video`), '풀영상 만들기')
}

export async function getRebuildStatus(key: string): Promise<RebuildStatus> {
  return jsonOrThrow(await fetch(`${BASE}/${key}/full-video/status`), '풀영상 만들기 상태 확인')
}

export interface DeleteGameResult {
  deletedFullVideo: boolean
  deletedClips: number
  freedBytes: number
}

export async function deleteGameFiles(key: string, target: 'fullVideo' | 'clips' | 'both' | 'all'): Promise<DeleteGameResult> {
  return jsonOrThrow(await send('POST', `${BASE}/${key}/delete`, { target }), '삭제')
}

export async function unsaveCandidate(key: string, id: string): Promise<Candidate> {
  return jsonOrThrow(await send('POST', `${BASE}/${key}/candidates/${id}/unsave`), '보관 해제')
}
