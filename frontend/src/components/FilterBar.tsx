import { useTuningUi } from '../appInfo'
import { TAG_LABELS } from '../labels'
import type { ClipSort } from '../grouping'
import type { ViewMode } from '../viewMode'
import type { ClipTag } from '../types'

const ALL_TAGS: ClipTag[] = ['kill', 'assist', 'death', 'teammate_death', 'no_result']

export interface FilterState {
  tags: ClipTag[]
  dayNight: string
  gameMode: string
  pinnedOnly: boolean
  trashed: boolean
  sort: ClipSort
  label: '' | 'unlabeled' | 'pvp' | 'pve' | 'conflict'
  minPvpScore: number
}

export const DEFAULT_FILTER: FilterState = {
  tags: [],
  dayNight: '',
  gameMode: '',
  pinnedOnly: false,
  trashed: false,
  sort: 'desc',
  label: '',
  minPvpScore: 0,
}

interface Props {
  value: FilterState
  onChange: (next: FilterState) => void
  variant?: 'steam' | 'vod'
  viewMode: ViewMode
  onViewModeChange: (mode: ViewMode) => void
}

const SELECT = 'rounded border border-zinc-600 bg-zinc-900 px-2 py-1 text-sm'

export function FilterBar({ value, onChange, variant = 'steam', viewMode, onViewModeChange }: Props) {
  const tuning = useTuningUi()
  const toggleTag = (tag: ClipTag) => {
    const has = value.tags.includes(tag)
    onChange({ ...value, tags: has ? value.tags.filter((t) => t !== tag) : [...value.tags, tag] })
  }

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-zinc-700 bg-zinc-800/40 px-4 py-3">
      <div className="flex overflow-hidden rounded border border-zinc-600 text-sm" role="group" aria-label="보기 모드">
        {(['cards', 'timeline'] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            aria-pressed={viewMode === mode}
            className={`px-3 py-1 ${viewMode === mode ? 'bg-sky-600 text-white' : 'bg-zinc-900 text-zinc-300 hover:bg-zinc-700'}`}
            onClick={() => onViewModeChange(mode)}
          >
            {mode === 'cards' ? '카드' : '일자 타임라인'}
          </button>
        ))}
      </div>

      <select
        className={SELECT}
        value={value.sort}
        onChange={(e) => onChange({ ...value, sort: e.target.value as FilterState['sort'] })}
      >
        {variant === 'vod' ? (
          <>
            <option value="asc">영상 시간순</option>
            <option value="desc">영상 역순</option>
          </>
        ) : (
          <>
            <option value="desc">최신 순</option>
            <option value="asc">오래된 순</option>
          </>
        )}
        <option value="pvp">교전 가능성순</option>
      </select>

      <select
        className={SELECT}
        value={value.label}
        onChange={(e) => onChange({ ...value, label: e.target.value as FilterState['label'] })}
      >
        <option value="">라벨 전체</option>
        <option value="unlabeled">라벨 없음</option>
        <option value="conflict">옮겨 온 라벨 (확인 필요)</option>
        <option value="pvp">교전 라벨</option>
        <option value="pve">사냥 라벨</option>
      </select>

      {tuning && (
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          교전 점수 {Math.round(value.minPvpScore * 100)}% 이상
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={Math.round(value.minPvpScore * 100)}
            onChange={(e) => onChange({ ...value, minPvpScore: Number(e.target.value) / 100 })}
          />
        </label>
      )}

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
        className={SELECT}
        value={value.dayNight}
        onChange={(e) => onChange({ ...value, dayNight: e.target.value })}
      >
        <option value="">낮/밤 전체</option>
        <option value="day">낮</option>
        <option value="night">밤</option>
      </select>

      <select
        className={SELECT}
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
        고정한 클립만
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
