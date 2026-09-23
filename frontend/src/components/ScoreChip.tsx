import { useTuningUi } from '../appInfo'
import { SIGNAL_LABELS } from '../labels'
import { scorePercent, scoreTone, type ScoreTone } from '../labeling'

const TONES: Record<ScoreTone, string> = {
  confirmed: 'border-emerald-500/60 bg-emerald-500/20 text-emerald-200',
  likely: 'border-amber-500/60 bg-amber-500/20 text-amber-200',
  weak: 'border-zinc-500/60 bg-zinc-500/20 text-zinc-300',
  none: 'border-zinc-700 bg-zinc-800 text-zinc-500',
}

interface Props {
  score: number | null
  signals: string[]
}

export function ScoreChip({ score, signals }: Props) {
  if (!useTuningUi()) return null
  const reason = signals.length ? signals.map((s) => SIGNAL_LABELS[s] ?? s).join(' · ') : '근거 없음'
  return (
    <span
      className={`rounded border px-1.5 py-0.5 text-xs font-semibold tabular-nums ${TONES[scoreTone(score)]}`}
      title={`교전 가능성 근거: ${reason}`}
    >
      교전 {scorePercent(score)}
    </span>
  )
}
