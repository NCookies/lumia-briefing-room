export type DeleteSourceAfter = 'ask' | 'always' | 'never'
export type DeleteSourceMode = 'trash' | 'permanent'

/** plan-vod.md V7 — always/never 는 묻지 않고 바로 정해지고, ask 만 매번 확인 창이 필요하다. */
export function resolvedDeleteSource(after: DeleteSourceAfter): boolean | null {
  if (after === 'always') return true
  if (after === 'never') return false
  return null
}

/** V7 (2): 항상 삭제 + 영구 삭제를 함께 고르면 확인도 복구도 없이 지워지므로 저장 전에 한 번 더 경고한다. */
export function needsAlwaysPermanentWarning(after: DeleteSourceAfter, mode: DeleteSourceMode): boolean {
  return after === 'always' && mode === 'permanent'
}
