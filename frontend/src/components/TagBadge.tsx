import type { ClipTag } from '../types'

const STYLES: Record<ClipTag, string> = {
  kill: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
  assist: 'bg-sky-500/20 text-sky-300 border-sky-500/40',
  death: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
  no_result: 'bg-zinc-500/20 text-zinc-300 border-zinc-500/40',
}

const LABELS: Record<ClipTag, string> = {
  kill: '킬',
  assist: '어시스트',
  death: '사망',
  no_result: '무성과',
}

export function TagBadge({ tag }: { tag: ClipTag }) {
  return (
    <span
      className={`rounded border px-1.5 py-0.5 text-xs font-medium ${STYLES[tag] ?? STYLES.no_result}`}
    >
      {LABELS[tag] ?? tag}
    </span>
  )
}
