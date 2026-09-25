export interface ActivityTask {
  id: number
  kind: string
  label: string
  startedAt: number
}

export const REFRESH_INTERVAL_MS = 5000
export const ACTIVITY_POLL_MS = 3000

interface RefreshInput {
  wasBusy: boolean
  busy: boolean
  msSinceRefresh: number
  intervalMs: number
}

export function shouldRefresh(o: RefreshInput): boolean {
  if (o.wasBusy && !o.busy) return true
  return o.busy && o.msSinceRefresh >= o.intervalMs
}

export function activityLabels(tasks: ActivityTask[], backfillLabel: string | null): string[] {
  const labels = tasks.map((t) => t.label)
  if (backfillLabel) labels.push(backfillLabel)
  return labels
}
