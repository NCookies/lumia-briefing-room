export interface RetentionSettings {
  autoCleanEnabled: boolean
  deleteMode: 'trash' | 'permanent'
  trashDays: number
  maxAgeDays: number | null
  maxCount: number | null
  maxTotalGb: number | null
  protectPinned: boolean
  protectTags: string[]
  keepGameRecords: boolean
}

export interface CleanupResult {
  toTrash: number
  toPurge: number
  bytesToFree: number
  applied: boolean
}

export function parseLimit(text: string): number | null {
  const value = Number(text.trim())
  return text.trim() !== '' && Number.isFinite(value) && value > 0 ? value : null
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${bytes} B`
}

export function describeCleanup(result: CleanupResult): string {
  if (result.toTrash === 0 && result.toPurge === 0) return '정리할 항목이 없습니다'
  return `휴지통으로 이동 ${result.toTrash}개 · 영구 삭제 ${result.toPurge}개 · ${formatBytes(result.bytesToFree)}`
}
