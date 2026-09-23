const BASE = '/api'

export type ClipsSource = 'steam' | 'vod'

const CONFIG_KEY: Record<ClipsSource, 'clips' | 'vodClips'> = { steam: 'clips', vod: 'vodClips' }

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

const send = (url: string, method: string, body: unknown) =>
  fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export async function getClipsDir(source: ClipsSource): Promise<string> {
  const cfg = await jsonOrThrow<{ paths?: Record<string, string | null> }>(await fetch(`${BASE}/config`), '설정 조회')
  return cfg.paths?.[CONFIG_KEY[source]] ?? ''
}

export async function setClipsDirOnly(source: ClipsSource, path: string): Promise<void> {
  await jsonOrThrow(await send(`${BASE}/config`, 'PUT', { paths: { [CONFIG_KEY[source]]: path } }), '설정 저장')
}

export async function moveClipsDir(source: ClipsSource, path: string): Promise<number> {
  const result = await jsonOrThrow<{ moved: number }>(
    await send(`${BASE}/clips-dir/move`, 'POST', { source, path }),
    '클립 옮기기',
  )
  return result.moved
}
