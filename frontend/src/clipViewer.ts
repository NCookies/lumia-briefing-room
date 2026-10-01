import type { ViewerAction } from './viewerShortcuts.ts'

/** 클립 → 그 클립을 만든 게임·후보. 서버가 게임 기록의 `savedClipId` 로 찾는다. */
export interface ClipSource {
  gameKey: string
  candidateId: string
  source: 'steam' | 'vod'
  hasFullVideo: boolean
}

export type RangeFixTarget =
  | { kind: 'game'; tab: 'steam' | 'vod'; gameKey: string; candidateId: string }
  | { kind: 'trim' }

/** 범위는 풀영상 화면에서 고친다. 게임이 없거나 풀영상이 지워진 클립(앱 밖 영상 포함)만 클립 자체를 자른다. */
export function rangeFixTarget(source: ClipSource | null): RangeFixTarget {
  if (!source || !source.hasFullVideo) return { kind: 'trim' }
  return { kind: 'game', tab: source.source, gameKey: source.gameKey, candidateId: source.candidateId }
}

/** 클립 재생 화면이 받는 단축키. 범위 편집 키는 풀영상 화면 몫이다. */
export const CLIP_VIEWER_ACTIONS: ViewerAction[] = [
  'togglePlay',
  'fullscreen',
  'volumeUp',
  'volumeDown',
  'seekBack',
  'seekForward',
  'prevClip',
  'nextClip',
  'archivePopup',
  'deleteClip',
  'memo',
  'help',
]

export function clipViewerAction(action: ViewerAction | null): ViewerAction | null {
  return action !== null && CLIP_VIEWER_ACTIONS.includes(action) ? action : null
}

export function neighborClipId(ids: string[], currentId: string, direction: 'prev' | 'next'): string | null {
  const at = ids.indexOf(currentId)
  if (at < 0) return null
  return ids[direction === 'next' ? at + 1 : at - 1] ?? null
}

/** 클립을 지우거나 옮긴 뒤 보일 클립: 다음, 없으면 이전, 둘 다 없으면 null(목록으로). */
export function idAfterRemoval(ids: string[], removedId: string): string | null {
  const at = ids.indexOf(removedId)
  if (at < 0) return null
  return ids[at + 1] ?? ids[at - 1] ?? null
}
