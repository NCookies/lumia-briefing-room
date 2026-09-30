export interface RetentionSettings {
  autoCleanEnabled: boolean
  deleteMode: 'recycle' | 'permanent'
  maxAgeDays: number | null
  maxCount: number | null
  maxTotalGb: number | null
  protectPinned: boolean
  protectTags: string[]
  keepGameRecords: boolean
  preserveBeforeDelete: boolean
}

export interface CleanupResult {
  toDelete: number
  bytesToFree: number
  applied: boolean
  preserveClips?: number
  heldBack?: number
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
  const notes: string[] = []
  if (result.toDelete > 0) notes.push(`${result.toDelete}개 삭제 · ${formatBytes(result.bytesToFree)}`)
  if (result.preserveClips) notes.push(`지우기 전에 클립 ${result.preserveClips}개를 남깁니다`)
  if (result.heldBack) notes.push(`클립을 남기지 못한 ${result.heldBack}개는 지우지 않았습니다`)
  return notes.length > 0 ? notes.join(' · ') : '정리할 항목이 없습니다'
}
