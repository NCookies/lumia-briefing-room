import type { Category } from './categoriesApi.ts'

export interface PopupRow {
  name: string
  clipCount: number
  thumbnailClipId: string | null
  checked: boolean
  selectable: boolean
}

/** "보관 위치" 팝업 줄. `자동 보관` 은 앱이 자동으로 채우는 칸이라 직접 고를 수 없고, 지금 거기 있는 클립일 때만 체크된 채 보인다. */
export function popupRows(categories: Category[], current: string | null): PopupRow[] {
  return categories
    .filter((c) => !c.auto || c.name === current)
    .map((c) => ({
      name: c.name,
      clipCount: c.clipCount,
      thumbnailClipId: c.thumbnailClipId,
      checked: c.name === current,
      selectable: !c.auto,
    }))
}

/** 후보 한 줄의 보관 상태: 보관 안 함 / 보관됨 / 보관했지만 범위를 고쳐 저장 대기. */
export function archiveState(saved: boolean, modified: boolean): 'none' | 'archived' | 'pending' {
  if (!saved) return 'none'
  return modified ? 'pending' : 'archived'
}
