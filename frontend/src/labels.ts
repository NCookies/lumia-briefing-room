import type { ClipTag } from './types'

export const TAG_LABELS: Record<ClipTag, string> = {
  kill: '킬',
  assist: '어시스트',
  death: '사망',
  teammate_death: '팀원 사망',
  team_wipe: '팀 전멸',
  no_result: '무성과',
}

export const SIGNAL_LABELS: Record<string, string> = {
  kill_delta: '킬 증가',
  assist_delta: '어시스트 증가',
  death: '내 사망',
  teammate_death: '팀원 사망',
  enemy_rings: '미니맵 적',
  ultimate_used: '궁극기 사용',
}
