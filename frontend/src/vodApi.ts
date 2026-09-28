import type { Vod } from './vodGrouping'
import type { DeleteSourceAfter, DeleteSourceMode } from './vodDeleteSource'

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
  return jsonOrThrow(await fetch(`${BASE}/vods`), '영상 파일 목록 불러오기')
}

export async function setStreamer(id: string, streamer: string): Promise<void> {
  await jsonOrThrow(await send(`${BASE}/vods/${id}`, 'PATCH', { streamer }), '스트리머 이름 저장')
}

export async function setVideoDate(id: string, date: string): Promise<void> {
  await jsonOrThrow(await send(`${BASE}/vods/${id}`, 'PATCH', { date }), '영상 날짜 저장')
}

export async function startAnalysis(
  id: string,
  options: { force?: boolean; rebuild?: boolean; deleteSource?: boolean } = {},
): Promise<void> {
  await jsonOrThrow(await send(`${BASE}/vods/${id}/analyze`, 'POST', options), '분석 시작')
}

export async function getAnalysis(id: string): Promise<AnalysisJob> {
  return jsonOrThrow(await fetch(`${BASE}/vods/${id}/analyze`), '분석 상태 확인')
}

export async function cancelAnalysis(id: string): Promise<void> {
  await jsonOrThrow(await send(`${BASE}/vods/${id}/analyze/cancel`, 'POST'), '분석 취소')
}

export async function deleteVodClips(id: string): Promise<number> {
  return (await jsonOrThrow<{ count: number }>(await send(`${BASE}/vods/${id}/clips`, 'DELETE'), '삭제')).count
}

export async function pickVideoFiles(initial = ''): Promise<string[]> {
  const { paths } = await jsonOrThrow<{ paths: string[] }>(
    await send(`${BASE}/fs/pick-videos`, 'POST', { initial }),
    '파일 선택',
  )
  return paths
}

export interface VodSettings {
  sources: string[]
  recursive: boolean
  deleteSourceAfter: DeleteSourceAfter
  deleteSourceMode: DeleteSourceMode
}

export async function getVodSettings(): Promise<VodSettings & { vodClips: string }> {
  const cfg = await jsonOrThrow<{
    vod?: {
      sources?: string[]
      recursive?: boolean
      deleteSourceAfter?: DeleteSourceAfter
      deleteSourceMode?: DeleteSourceMode
    }
    paths?: { vodClips?: string | null }
  }>(await fetch(`${BASE}/config`), '설정 불러오기')
  return {
    sources: cfg.vod?.sources ?? [],
    recursive: cfg.vod?.recursive ?? false,
    deleteSourceAfter: cfg.vod?.deleteSourceAfter ?? 'ask',
    deleteSourceMode: cfg.vod?.deleteSourceMode ?? 'trash',
    vodClips: cfg.paths?.vodClips ?? '',
  }
}

export async function saveVodSettings(patch: { vod?: Partial<VodSettings>; paths?: { vodClips?: string } }): Promise<void> {
  await jsonOrThrow(await send(`${BASE}/config`, 'PUT', patch), '설정 저장')
}

export async function getDeleteSourceAfter(): Promise<DeleteSourceAfter> {
  const cfg = await jsonOrThrow<{ vod?: { deleteSourceAfter?: DeleteSourceAfter } }>(
    await fetch(`${BASE}/config`), '설정 불러오기',
  )
  return cfg.vod?.deleteSourceAfter ?? 'ask'
}

export async function setDeleteSourceAfter(deleteSourceAfter: DeleteSourceAfter): Promise<void> {
  await jsonOrThrow(await send(`${BASE}/config`, 'PUT', { vod: { deleteSourceAfter } }), '설정 저장')
}
