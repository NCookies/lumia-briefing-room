export type ClipTag =
  | 'kill'
  | 'assist'
  | 'death'
  | 'teammate_death'
  | 'team_wipe'
  | 'no_result'

export type UserLabel = 'pvp' | 'pve' | null

export interface MatchResult {
  matchType: 'rank' | 'normal' | 'unknown'
  matchLabel: string
  placement: number
  total: number
  outcome: string | null
  nickname: string | null
  character?: string | null
  characterRaw?: string | null
  imagePath?: string | null
  tk?: number | null
  kills?: number | null
  deaths?: number | null
  assists?: number | null
}

export interface Clip {
  id: string
  title: string
  sessionDir: string
  sessionStartUtc: string
  matchStartUtc: string
  gameMode: string
  sourceWidth: number
  sourceHeight: number
  segmentStart: number
  segmentEnd: number
  videoOffsetSec: number
  durationSec: number
  thumbnailPath: string | null
  sourceIncomplete: boolean
  audioStatus?: 'full' | 'partial' | 'none'
  combatStartOffsetSec: number
  combatEndOffsetSec: number
  prerollSource: string
  tags: ClipTag[]
  killDelta: number
  assistDelta: number
  died: boolean
  pvpScore: number | null
  pvpSignals: string[]
  teamWipe: string | null
  enemyRingMean: number | null
  region: string | null
  userLabel: UserLabel
  labelSource?: 'user' | 'migrated' | null
  labelConflict?: boolean
  gameDay: number | null
  dayNight: 'day' | 'night' | null
  phaseIndex: number | null
  reviveCost: 'free' | 'credit' | null
  myCharacter: string | null
  teamCharacters: string[]
  pinned: boolean
  deletedAt: string | null
  matchKills: number | null
  matchAssists: number | null
  matchTeamKills: number | null
  detectorConfidence: number
  sizeBytes?: number
  trimmed?: boolean
  originalDurationSec?: number
  matchResult?: MatchResult | null
}
