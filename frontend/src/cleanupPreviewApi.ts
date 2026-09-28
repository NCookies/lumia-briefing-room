import type { CleanupPreviewMap } from './cleanupPreview'

export async function getCleanupPreview(): Promise<CleanupPreviewMap> {
  const res = await fetch('/api/cleanup/preview')
  if (!res.ok) throw new Error(`삭제 예정 목록을 불러오지 못했습니다 (${res.status})`)
  return (await res.json()) as CleanupPreviewMap
}
