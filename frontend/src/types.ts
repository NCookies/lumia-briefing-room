export type ClipTag = 'kill' | 'assist' | 'death' | 'no_result'

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
  combatStartOffsetSec: number
  combatEndOffsetSec: number
  prerollSource: string
  tags: ClipTag[]
  killDelta: number
  assistDelta: number
  died: boolean
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
}
