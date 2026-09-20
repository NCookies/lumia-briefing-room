import type { UserLabel } from '../types'

interface Props {
  value: UserLabel
  onChange: (label: UserLabel) => void
  showKeys?: boolean
  size?: 'sm' | 'lg'
}

const OPTIONS: { label: 'pvp' | 'pve'; text: string; key: string; active: string }[] = [
  { label: 'pvp', text: '교전', key: '1', active: 'border-emerald-400 bg-emerald-500/30 text-emerald-100' },
  { label: 'pve', text: '사냥', key: '2', active: 'border-zinc-300 bg-zinc-500/40 text-zinc-100' },
]

export function LabelButtons({ value, onChange, showKeys = false, size = 'sm' }: Props) {
  const pad = size === 'lg' ? 'px-5 py-2 text-base' : 'px-2 py-0.5 text-xs'
  return (
    <div className="flex gap-1">
      {OPTIONS.map((o) => (
        <button
          key={o.label}
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onChange(value === o.label ? null : o.label)
          }}
          className={`rounded border font-medium ${pad} ${
            value === o.label ? o.active : 'border-zinc-600 text-zinc-400 hover:border-zinc-400'
          }`}
        >
          {o.text}
          {showKeys && <kbd className="ml-2 rounded bg-black/40 px-1 text-xs opacity-70">{o.key}</kbd>}
        </button>
      ))}
    </div>
  )
}
