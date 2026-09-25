interface Props {
  label: string
  detail?: string
  percent?: number
}

export function LoadingBar({ label, detail, percent }: Props) {
  return (
    <div className="flex w-full max-w-md flex-col gap-1.5" role="status" aria-live="polite">
      <div className="flex items-baseline justify-between text-sm text-zinc-300">
        <span>{label}</span>
        {percent !== undefined && <span className="tabular-nums text-zinc-400">{percent}%</span>}
      </div>
      <div className="h-1.5 overflow-hidden rounded bg-zinc-700">
        {percent === undefined ? (
          <div className="indeterminate-bar h-full rounded bg-sky-500" />
        ) : (
          <div className="h-full rounded bg-sky-500 transition-[width]" style={{ width: `${percent}%` }} />
        )}
      </div>
      {detail && <p className="text-xs text-zinc-500">{detail}</p>}
    </div>
  )
}
