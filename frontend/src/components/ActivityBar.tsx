interface Props {
  labels: string[]
}

export function ActivityBar({ labels }: Props) {
  if (labels.length === 0) return null
  return (
    <div className="border-b border-sky-900/60 bg-sky-950/40" role="status" aria-live="polite">
      <div className="h-0.5 overflow-hidden bg-sky-900/60">
        <div className="indeterminate-bar h-full bg-sky-400" />
      </div>
      <p className="px-4 py-1 text-xs text-sky-200">
        {labels.join(' · ')}
        <span className="ml-2 text-sky-400/70">끝나면 목록이 자동으로 갱신됩니다</span>
      </p>
    </div>
  )
}
