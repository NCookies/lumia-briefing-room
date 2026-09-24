export type ViewMode = 'cards' | 'timeline'

const key = (source: string) => `lumia.viewMode.${source}`

export function parseViewMode(raw: string | null | undefined): ViewMode {
  return raw === 'timeline' ? 'timeline' : 'cards'
}

export function loadViewMode(source: string): ViewMode {
  try {
    return parseViewMode(localStorage.getItem(key(source)))
  } catch {
    return 'cards'
  }
}

export function saveViewMode(source: string, mode: ViewMode): void {
  try {
    localStorage.setItem(key(source), mode)
  } catch {
    // 저장 실패는 무시한다
  }
}
