import type { Clip } from './types'

const BASE = '/api/library'

export interface LibraryFolder {
  name: string
  rel: string
  clipCount: number
}

export interface LibraryClip extends Clip {
  relPath: string
  fileName: string
  unknownVideo?: boolean
  sizeBytes?: number
}

export interface LibraryListing {
  path: string
  layout: 'new' | 'legacy'
  virtualTop: boolean
  crumbs: { name: string; rel: string }[]
  folders: LibraryFolder[]
  clips: LibraryClip[]
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

const send = (url: string, method: string, body: unknown) =>
  fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export async function getLibrary(path: string): Promise<LibraryListing> {
  const listing = await jsonOrThrow<LibraryListing>(
    await fetch(`${BASE}?path=${encodeURIComponent(path)}`),
    '클립 폴더 불러오기',
  )
  return { ...listing, clips: listing.clips.map((c) => ({ ...c, userLabel: c.userLabel ?? null })) }
}

export async function createFolder(path: string, name: string): Promise<string> {
  return (await jsonOrThrow<{ path: string }>(await send(`${BASE}/folders`, 'POST', { path, name }), '폴더 만들기')).path
}

export async function renameEntry(path: string, name: string): Promise<string> {
  return (await jsonOrThrow<{ path: string }>(await send(`${BASE}/rename`, 'PATCH', { path, name }), '이름 바꾸기')).path
}

export async function moveEntries(items: string[], dest: string): Promise<void> {
  await jsonOrThrow(await send(`${BASE}/move`, 'POST', { items, dest }), '옮기기')
}

export async function deleteEntries(items: string[]): Promise<void> {
  await jsonOrThrow(await send(`${BASE}/delete`, 'POST', { items }), '삭제')
}

export async function revealEntry(path: string): Promise<void> {
  await jsonOrThrow(await send(`${BASE}/reveal`, 'POST', { path }), '탐색기 열기')
}

export async function exportEntries(items: string[], dir: string): Promise<string[]> {
  return (await jsonOrThrow<{ paths: string[] }>(await send(`${BASE}/export`, 'POST', { items, dir }), '내보내기')).paths
}
