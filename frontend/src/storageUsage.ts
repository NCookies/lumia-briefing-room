import { formatBytes } from './retention.ts'

export type UsageLevel = 'ok' | 'warn' | 'full'

export interface StorageUsage {
  percent: number
  level: UsageLevel
  label: string
}

const WARN_RATIO = 0.75
const FULL_RATIO = 0.9

interface Input {
  tabBytes: number
  totalBytes: number
  limitGb: number | null
  autoCleanEnabled: boolean
  showTabShare?: boolean
}

/** 풀영상 용량 막대. 한도는 스팀 녹화·영상 파일 합산 하나라 전체 합계로 비율을 잡고, 이 탭의 몫은 글자로만 알린다. 한도가 없으면 null(숨김). */
export function storageUsage({ tabBytes, totalBytes, limitGb, autoCleanEnabled, showTabShare = true }: Input): StorageUsage | null {
  if (!autoCleanEnabled || limitGb == null || !(limitGb > 0)) return null
  const ratio = totalBytes / (limitGb * 1024 ** 3)
  const level: UsageLevel = ratio >= FULL_RATIO ? 'full' : ratio >= WARN_RATIO ? 'warn' : 'ok'
  const share = showTabShare ? `이 탭 ${formatBytes(tabBytes)} · 전체 ` : ''
  return {
    percent: Math.min(100, Math.max(0, ratio * 100)),
    level,
    label: `${share}${formatBytes(totalBytes)} / ${limitGb} GB`,
  }
}
