const BASE = '/api/categories'

export interface Category {
  name: string
  auto: boolean
  default: boolean
  clipCount: number
  thumbnailClipId: string | null
}

export interface CategoryList {
  enabled: boolean
  categories: Category[]
}

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

const post = (url: string, body: unknown) =>
  fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export async function getCategories(): Promise<CategoryList> {
  return jsonOrThrow(await fetch(BASE), '카테고리 불러오기')
}

export async function createCategory(name: string): Promise<string> {
  return (await jsonOrThrow<{ name: string }>(await post(BASE, { name }), '카테고리 만들기')).name
}

export async function moveClipsToCategory(clipIds: string[], category: string): Promise<number> {
  return (await jsonOrThrow<{ moved: number }>(await post(`${BASE}/move`, { clipIds, category }), '카테고리 옮기기')).moved
}
