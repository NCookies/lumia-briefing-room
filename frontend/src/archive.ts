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

/** 후보 한 줄의 보관 상태: 보관 안 함 / 보관됨 / 보관했지만 범위를 고쳐 저장 대기. */
export function archiveState(saved: boolean, modified: boolean): 'none' | 'archived' | 'pending' {
  if (!saved) return 'none'
  return modified ? 'pending' : 'archived'
}
