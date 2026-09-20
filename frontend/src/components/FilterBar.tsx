import type { ClipTag } from '../types'

const ALL_TAGS: ClipTag[] = ['kill', 'assist', 'death', 'no_result']
const TAG_LABELS: Record<ClipTag, string> = {
  kill: '킬',
  assist: '어시스트',
  death: '사망',
  no_result: '무성과',
}

export interface FilterState {
  tags: ClipTag[]
  dayNight: string
  gameMode: string
  pinnedOnly: boolean
  trashed: boolean
}

export const DEFAULT_FILTER: FilterState = {
  tags: [],
  dayNight: '',
  gameMode: '',
  pinnedOnly: false,
  trashed: false,
}

interface Props {
  value: FilterState
  onChange: (next: FilterState) => void
}

export function FilterBar({ value, onChange }: Props) {
  const toggleTag = (tag: ClipTag) => {
    const has = value.tags.includes(tag)
    onChange({ ...value, tags: has ? value.tags.filter((t) => t !== tag) : [...value.tags, tag] })
  }

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-zinc-700 bg-zinc-800/40 px-4 py-3">
      <div className="flex gap-1">
        {ALL_TAGS.map((tag) => (
          <button
            key={tag}
            type="button"
            onClick={() => toggleTag(tag)}
            className={`rounded border px-2 py-1 text-xs ${
              value.tags.includes(tag)
                ? 'border-sky-500 bg-sky-500/20 text-sky-200'
                : 'border-zinc-600 text-zinc-400 hover:border-zinc-400'
            }`}
          >
            {TAG_LABELS[tag]}
          </button>
        ))}
      </div>

      <select
        className="rounded border border-zinc-600 bg-zinc-900 px-2 py-1 text-sm"
        value={value.dayNight}
        onChange={(e) => onChange({ ...value, dayNight: e.target.value })}
      >
        <option value="">낮/밤 전체</option>
        <option value="day">낮</option>
        <option value="night">밤</option>
      </select>

      <select
        className="rounded border border-zinc-600 bg-zinc-900 px-2 py-1 text-sm"
        value={value.gameMode}
        onChange={(e) => onChange({ ...value, gameMode: e.target.value })}
      >
        <option value="">모드 전체</option>
        <option value="battle_royale">배틀로얄</option>
        <option value="cobalt">코발트 프로토콜</option>
      </select>

      <label className="flex items-center gap-1 text-sm text-zinc-300">
        <input
          type="checkbox"
          checked={value.pinnedOnly}
          onChange={(e) => onChange({ ...value, pinnedOnly: e.target.checked })}
        />
        고정만
      </label>

      <div className="ml-auto flex rounded border border-zinc-600 text-sm">
        <button
          type="button"
          className={`px-3 py-1 ${!value.trashed ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-400'}`}
          onClick={() => onChange({ ...value, trashed: false })}
        >
          클립
        </button>
        <button
          type="button"
          className={`px-3 py-1 ${value.trashed ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-400'}`}
          onClick={() => onChange({ ...value, trashed: true })}
        >
          휴지통
        </button>
      </div>
    </div>
  )
}
