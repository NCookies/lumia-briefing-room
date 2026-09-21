import type { Vod } from './vodGrouping'

const BASE = '/api'

export interface AnalysisJob {
  id: string
  state: 'idle' | 'running' | 'done' | 'error' | 'cancelled'
  phase?: 'decode' | 'games' | 'cut' | 'done'
  fraction?: number
  games?: number
  clips?: number
  message?: string
}

export interface VideoListing {
  path: string
  parent: string | null
  dirs: string[]
  files: { name: string; sizeBytes: number }[]
}

async function jsonOrThrow<T>(res: Response, action: string): Promise<T> {
  if (!res.ok) {
    let detail = ''
    try {
      detail = (await res.json()).detail ?? ''
    } catch {
      // 본문이 JSON 이 아니면 상태 코드만 보여준다
    }
    throw new Error(detail || `${action}에 실패했습니다 (${res.status})`)
  }
  return res.json()
}

const send = (url: string, method: string, body?: unknown) =>
  fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

export async function listVods(): Promise<Vod[]> {
  return jsonOrThrow(await fetch(`${BASE}/vods`), '다시보기 목록 조회')
}

export async function setStreamer(id: string, streamer: string): Promise<void> {
  await jsonOrThrow(await send(`${BASE}/vods/${id}`, 'PATCH', { streamer }), '스트리머 이름 저장')
}

export async function startAnalysis(id: string, options: { force?: boolean; rebuild?: boolean } = {}): Promise<void> {
  await jsonOrThrow(await send(`${BASE}/vods/${id}/analyze`, 'POST', options), '분석 시작')
}

export async function getAnalysis(id: string): Promise<AnalysisJob> {
  return jsonOrThrow(await fetch(`${BASE}/vods/${id}/analyze`), '분석 상태 조회')
}

export async function cancelAnalysis(id: string): Promise<void> {
  await jsonOrThrow(await send(`${BASE}/vods/${id}/analyze/cancel`, 'POST'), '분석 취소')
}

export async function trashVodClips(id: string): Promise<number> {
  return (await jsonOrThrow<{ count: number }>(await send(`${BASE}/vods/${id}/trash`, 'POST'), '삭제')).count
}

export async function restoreVodClips(id: string): Promise<number> {
  return (await jsonOrThrow<{ count: number }>(await send(`${BASE}/vods/${id}/restore`, 'POST'), '복구')).count
}

export async function deleteVodClipsForever(id: string): Promise<number> {
  return (await jsonOrThrow<{ count: number }>(await send(`${BASE}/vods/${id}/clips`, 'DELETE'), '완전 삭제')).count
}

export async function listVideos(path: string): Promise<VideoListing> {
  return jsonOrThrow(await fetch(`${BASE}/fs/videos?${new URLSearchParams({ path })}`), '폴더 조회')
}

export interface VodSettings {
  sources: string[]
  recursive: boolean
}

export async function getVodSettings(): Promise<VodSettings & { vodClips: string }> {
  const cfg = await jsonOrThrow<{
    vod?: { sources?: string[]; recursive?: boolean }
    paths?: { vodClips?: string | null }
  }>(await fetch(`${BASE}/config`), '설정 조회')
  return {
    sources: cfg.vod?.sources ?? [],
    recursive: cfg.vod?.recursive ?? false,
    vodClips: cfg.paths?.vodClips ?? '',
  }
}

export async function saveVodSettings(patch: { vod?: Partial<VodSettings>; paths?: { vodClips?: string } }): Promise<void> {
  await jsonOrThrow(await send(`${BASE}/config`, 'PUT', patch), '설정 저장')
}
