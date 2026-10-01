import { formatBytes } from './retention.ts'

export type DeleteTarget = 'fullVideo' | 'clips' | 'both' | 'all'

export interface DeletableGame {
  hasFullVideo: boolean
  fullVideoSizeBytes: number | null
  /** 사용자가 보관한 클립 수(`자동 보관` 밖). 클립 삭제가 남긴다. */
  savedClipCount: number
  /** `자동 보관` 카테고리의 클립 수. 클립 삭제가 지운다. */
  autoClipCount: number
  pinned: boolean
}

export interface DeleteMenuItem {
  target: DeleteTarget
  label: string
  disabled: boolean
}

export function deleteMenuItems(game: DeletableGame): DeleteMenuItem[] {
  return [
    { target: 'fullVideo', label: '풀영상만 삭제', disabled: !game.hasFullVideo },
    { target: 'clips', label: '자동 보관 클립 삭제', disabled: game.autoClipCount === 0 },
    { target: 'all', label: '게임 전체 삭제', disabled: false },
  ]
}

export function deleteWarning(game: DeletableGame, target: DeleteTarget): string {
  if (target === 'all') {
    const what = [game.hasFullVideo ? '풀영상' : null, game.savedClipCount > 0 ? `클립 ${game.savedClipCount}개` : null, '게임 기록(결과·후보)']
    const lines = [`이 게임을 목록에서 완전히 삭제합니다. ${what.filter(Boolean).join(', ')}이(가) 모두 지워집니다.`]
    if (game.pinned) lines.push('고정한 게임입니다. 자동 정리에서 제외해 둔 게임을 지우려는 것이 맞나요?')
    return lines.join('\n')
  }
  const parts: string[] = []
  if (target !== 'clips' && game.hasFullVideo) {
    parts.push(game.fullVideoSizeBytes != null ? `풀영상 ${formatBytes(game.fullVideoSizeBytes)}` : '풀영상')
  }
  if (target !== 'fullVideo' && game.autoClipCount > 0) parts.push(`자동 보관 클립 ${game.autoClipCount}개`)
  let first = `이 게임의 ${parts.join('과 ')}을(를) 삭제합니다.`
  if (target !== 'fullVideo' && game.savedClipCount > 0) first += ` 보관한 클립 ${game.savedClipCount}개는 남습니다.`
  const lines = [`${first} 게임 기록(결과·후보)은 남습니다.`]
  if (game.pinned) lines.push('고정한 게임입니다. 자동 정리에서 제외해 둔 게임을 지우려는 것이 맞나요?')
  return lines.join('\n')
}

/** 고정한 게임은 "다시 묻지 않기"를 켰어도 묻는다. */
export function mustAskBeforeDelete(game: DeletableGame, confirmDelete: boolean): boolean {
  return confirmDelete || game.pinned
}
