import { storageUsage, type UsageLevel } from '../storageUsage'
import type { StorageTotals } from '../useStorageUsage'

const FILL: Record<UsageLevel, string> = {
  ok: 'bg-sky-500',
  warn: 'bg-amber-500',
  full: 'bg-rose-500',
}

const TEXT: Record<UsageLevel, string> = {
  ok: 'text-zinc-400',
  warn: 'text-amber-300',
  full: 'text-rose-300',
}

interface Props {
  totals: StorageTotals | null
  tabBytes: number
}

/** "게임 N개" 줄 옆 풀영상 용량 막대. 자동 정리 한도가 없으면 그리지 않는다. */
export function StorageUsageBar({ totals, tabBytes }: Props) {
  if (!totals) return null
  const usage = storageUsage({ tabBytes, totalBytes: totals.totalBytes, limitGb: totals.limitGb, autoCleanEnabled: totals.autoCleanEnabled })
  if (!usage) return null
  return (
    <span
      className="flex items-center gap-2"
      title="자동 정리 한도(스팀 녹화·영상 파일 풀영상 합산)에서 지금 쓰는 양입니다"
    >
      <span className="h-1.5 w-24 overflow-hidden rounded-md bg-zinc-700">
        <span className={`block h-full ${FILL[usage.level]}`} style={{ width: `${usage.percent}%` }} />
      </span>
      <span className={`text-xs ${TEXT[usage.level]}`}>{usage.label}</span>
    </span>
  )
}
