export type AdminMode = 'release' | 'dev'

export interface InstallRow {
  installId: string
  count: number
  combat: number
  other: number
  lastReceivedAt: string | null
}

export interface AdminSummary {
  total: number
  installs: number
  byLabel: Record<string, number>
  byVersion: Record<string, number>
  byResolution: Record<string, number>
  byDay: Record<string, number>
  lastReceivedAt: string | null
  perInstall: InstallRow[]
}

export interface AdminLabelItem {
  installId: string
  receivedAt: string
  appVersion: string
  label: { clipKey?: string; userLabel?: string; sourceWidth?: number; sourceHeight?: number }
}

export interface AdminLabelPage {
  total: number
  items: AdminLabelItem[]
}

export const ADMIN_PAGE_SIZE = 50

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = ''
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      // 본문이 JSON 이 아니면 상태 코드만 알린다
    }
    throw new Error(detail || `관리자 데이터 불러오기에 실패했습니다 (${res.status})`)
  }
  return res.json()
}

export const getAdminSummary = async (mode: AdminMode, refresh: boolean): Promise<AdminSummary> =>
  jsonOrThrow(await fetch(`/api/admin/summary?${new URLSearchParams({ mode, refresh: refresh ? '1' : '0' })}`))

export const getAdminLabels = async (
  mode: AdminMode,
  q: string,
  userLabel: string,
  offset: number,
): Promise<AdminLabelPage> =>
  jsonOrThrow(
    await fetch(
      `/api/admin/labels?${new URLSearchParams({ mode, q, userLabel, limit: String(ADMIN_PAGE_SIZE), offset: String(offset) })}`,
    ),
  )

export function pageRange(offset: number, total: number, size: number = ADMIN_PAGE_SIZE): string {
  if (total === 0) return '결과 없음'
  return `${offset + 1}–${Math.min(offset + size, total)} / ${total}`
}

export function barWidths(data: Record<string, number>): [string, number, number][] {
  const max = Math.max(1, ...Object.values(data))
  return Object.entries(data).map(([key, value]) => [key, value, Math.round((value / max) * 100)])
}
