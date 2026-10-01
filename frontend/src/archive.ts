import type { Category } from './categoriesApi.ts'

export interface PopupRow {
  name: string
  clipCount: number
  thumbnailClipId: string | null
  checked: boolean
  selectable: boolean
  /** 앱이 자동으로 채우는 칸이라 흐리게 보인다. */
  dim: boolean
}

/** "보관 위치" 팝업 줄. `자동 보관` 도 항상 보이며(맨 아래, 흐리게) 골라서 보관할 수 있다. */
export function popupRows(categories: Category[], current: string | null): PopupRow[] {
  return categories
    .map((c) => ({
      name: c.name,
      clipCount: c.clipCount,
      thumbnailClipId: c.thumbnailClipId,
      checked: c.name === current,
      selectable: true,
      dim: c.auto,
    }))
}

export interface RowState {
  /** 북마크 모양: 카테고리에 보관한 클립이면 채워진 `보관됨`, 아니면(클립이 없거나 자동 보관에 있어도) 빈 `보관`. */
  bookmark: 'none' | 'archived'
  /** 보관한 뒤 범위를 고쳐 `다시 저장`이 필요한가(클립이 있을 때만 - 자동 보관의 클립도 포함). */
  resave: boolean
  /** `클립 삭제` 버튼을 보일 수 있는가(보관됨 여부와 상관없이 클립 파일이 있으면). */
  deletable: boolean
}

/** 후보 한 줄의 상태. `hasClip` = 이 후보로 만든 클립 파일이 있다, `archived` = 그 클립이 자동 보관이 아닌 카테고리에 있다. */
export function rowState(hasClip: boolean, archived: boolean, modified: boolean): RowState {
  return { bookmark: hasClip && archived ? 'archived' : 'none', resave: hasClip && modified, deletable: hasClip }
}

export type PopupEntry = { kind: 'plain' } | { kind: 'row'; name: string } | { kind: 'new' }

/** 키보드로 오갈 수 있는 칸들(화면 위에서 아래 순서). 카테고리를 쓰지 않는 방식이면 `보관하기` 한 칸이 앞에 오고 `+ 새 카테고리` 는 없다. */
export function popupEntries(rows: PopupRow[], categoriesEnabled: boolean): PopupEntry[] {
  const list: PopupEntry[] = rows.map((r) => ({ kind: 'row', name: r.name }))
  return categoriesEnabled ? [...list, { kind: 'new' }] : [{ kind: 'plain' }, ...list]
}

export function stepHighlight(index: number, count: number, direction: 1 | -1): number {
  if (count <= 0) return 0
  return (index + direction + count) % count
}

export function initialHighlight(entries: PopupEntry[], current: string | null): number {
  const at = entries.findIndex((e) => e.kind === 'row' && e.name === current)
  return at < 0 ? 0 : at
}
