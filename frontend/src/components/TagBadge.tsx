import { TAG_LABELS } from '../labels'
import type { ClipTag } from '../types'

const STYLES: Record<ClipTag, string> = {
  kill: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
  assist: 'bg-sky-500/20 text-sky-300 border-sky-500/40',
  death: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
  teammate_death: 'bg-orange-500/20 text-orange-300 border-orange-500/40',
  team_wipe: 'bg-fuchsia-500/20 text-fuchsia-300 border-fuchsia-500/40',
  no_result: 'bg-zinc-500/20 text-zinc-300 border-zinc-500/40',
}

export function TagBadge({ tag }: { tag: ClipTag }) {
  return (
    <span
      className={`rounded border px-1.5 py-0.5 text-xs font-medium ${STYLES[tag] ?? STYLES.no_result}`}
    >
      {TAG_LABELS[tag] ?? tag}
    </span>
  )
}
