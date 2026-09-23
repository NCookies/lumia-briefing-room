import type { CleanupResult, RetentionSettings } from './retention'

const BASE = '/api'

export interface DirListing {
  path: string
  parent: string | null
  dirs: string[]
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

const postJson = (url: string, body: unknown, method = 'POST') =>
  fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export async function listDirs(path: string): Promise<DirListing> {
  return jsonOrThrow(await fetch(`${BASE}/fs/dirs?${new URLSearchParams({ path })}`), '폴더 조회')
}

export async function makeDir(path: string, name: string): Promise<{ path: string }> {
  return jsonOrThrow(await postJson(`${BASE}/fs/mkdir`, { path, name }), '폴더 만들기')
}

export async function exportClip(id: string, dir: string, filename: string): Promise<{ path: string }> {
  return jsonOrThrow(await postJson(`${BASE}/clips/${id}/export`, { dir, filename }), '저장')
}

export async function getExportDefault(): Promise<string> {
  const cfg = await jsonOrThrow<{ paths?: { exportDefault?: string | null } }>(
    await fetch(`${BASE}/config`),
    '설정 조회',
  )
  return cfg.paths?.exportDefault ?? ''
}

export async function getNickname(): Promise<string> {
  const cfg = await jsonOrThrow<{ player?: { nickname?: string } }>(await fetch(`${BASE}/config`), '설정 조회')
  return cfg.player?.nickname ?? ''
}

export async function setNickname(nickname: string): Promise<void> {
  await jsonOrThrow(await postJson(`${BASE}/config`, { player: { nickname } }, 'PUT'), '설정 저장')
}

export async function getRetention(): Promise<RetentionSettings> {
  const cfg = await jsonOrThrow<{ retention: RetentionSettings }>(await fetch(`${BASE}/config`), '설정 조회')
  return cfg.retention
}

export async function setRetention(retention: RetentionSettings): Promise<void> {
  await jsonOrThrow(await postJson(`${BASE}/config`, { retention }, 'PUT'), '설정 저장')
}

export async function runCleanup(dryRun: boolean): Promise<CleanupResult> {
  return jsonOrThrow(await postJson(`${BASE}/cleanup`, { dryRun }), '자동 정리')
}

export async function getConfirmDelete(): Promise<boolean> {
  const cfg = await jsonOrThrow<{ ui?: { confirmDelete?: boolean } }>(await fetch(`${BASE}/config`), '설정 조회')
  return cfg.ui?.confirmDelete ?? true
}

export async function setConfirmDelete(confirmDelete: boolean): Promise<void> {
  await jsonOrThrow(await postJson(`${BASE}/config`, { ui: { confirmDelete } }, 'PUT'), '설정 저장')
}

export async function setExportDefault(dir: string): Promise<void> {
  await jsonOrThrow(await postJson(`${BASE}/config`, { paths: { exportDefault: dir } }, 'PUT'), '설정 저장')
}

export async function getAutoStart(): Promise<boolean> {
  const cfg = await jsonOrThrow<{ ui?: { autoStart?: boolean } }>(await fetch(`${BASE}/config`), '설정 조회')
  return cfg.ui?.autoStart ?? true
}

export async function setAutoStart(autoStart: boolean): Promise<void> {
  await jsonOrThrow(await postJson(`${BASE}/config`, { ui: { autoStart } }, 'PUT'), '설정 저장')
}
