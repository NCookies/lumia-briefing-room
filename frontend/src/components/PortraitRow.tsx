import { characterPortraitUrl, type PortraitSlot } from '../api'
import type { Clip } from '../types'

interface Props {
  clip: Clip | undefined
}

const SLOTS: { slot: PortraitSlot; label: string; hasPath: (clip: Clip) => boolean }[] = [
  { slot: 'me', label: '내 캐릭터', hasPath: (c) => Boolean(c.myCharacterPortraitPath) },
  { slot: 'teammate1', label: '팀원', hasPath: (c) => Boolean(c.teammatePortraitPaths?.[0]) },
  { slot: 'teammate2', label: '팀원', hasPath: (c) => Boolean(c.teammatePortraitPaths?.[1]) },
]

/** 게임 행의 캐릭터 표시: 이름 텍스트 대신 캐릭터 선택 화면 초상화 3장(SPEC §2.10, plan-ui.md §0). */
export function PortraitRow({ clip }: Props) {
  return (
    <div className="flex gap-1">
      {SLOTS.map(({ slot, label, hasPath }) => (
        <div
          key={slot}
          className="h-10 w-10 shrink-0 overflow-hidden rounded border border-zinc-700 bg-zinc-900"
          title={label}
        >
          {clip && hasPath(clip) && (
            <img
              src={characterPortraitUrl(clip.id, slot)}
              alt={label}
              className="h-full w-full object-cover"
              onError={(e) => {
                e.currentTarget.style.display = 'none'
              }}
            />
          )}
        </div>
      ))}
    </div>
  )
}
