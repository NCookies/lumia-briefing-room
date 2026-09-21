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
    throw new Error(`${action} 실패 (${res.status})${detail ? `: ${detail}` : ''}`)
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

export async function setExportDefault(dir: string): Promise<void> {
  await jsonOrThrow(await postJson(`${BASE}/config`, { paths: { exportDefault: dir } }, 'PUT'), '설정 저장')
}
