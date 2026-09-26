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

export interface ModeStatus {
  labels: number
  logEntryFiles: number
  diagnostics: number
  installs: number
  lastReceived: { labels: string | null; logs: string | null; diagnostics: string | null }
}

export interface ServerStatus {
  release: ModeStatus
  dev: ModeStatus
  today: { requests: Record<string, number>; rejected: Record<string, number> }
  disk: { totalBytes: number; usedPercent: number; dataBytes: number }
  blockedIps: number
  retentionDays: number
  serverTime: string
}

export interface DiagnosticSummary {
  receiptId: string
  displayId: string | null
  installId: string
  receivedAt: string
  appVersion: string | null
  os: string | null
  entryCount: number
  errorCount: number
}

export interface LogEntry {
  installId: string
  receivedAt: string
  appVersion: string | null
  ts: string
  level: string
  logger?: string
  message: string
  exceptionType?: string
  stack?: string
  fingerprint?: string
}

export interface DiagnosticDetail {
  installId: string
  receiptId: string
  displayId: string | null
  receivedAt: string
  env: Record<string, unknown>
  entries: LogEntry[]
}

export interface LogGroup {
  fingerprint: string | null
  count: number
  installs: number
  level: string | null
  exceptionType: string | null
  message: string
  firstSeen: string
  lastSeen: string
}

export interface Listing<T> {
  total: number
  items: T[]
}

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

const get = async <T>(path: string, params: Record<string, string>): Promise<T> =>
  jsonOrThrow(await fetch(`${path}?${new URLSearchParams(params)}`))

export const getServerStatus = (): Promise<ServerStatus> => get('/api/admin/status', {})

export const getDiagnostics = (mode: AdminMode, q: string, offset: number): Promise<Listing<DiagnosticSummary>> =>
  get('/api/admin/diagnostics', { mode, q, limit: String(ADMIN_PAGE_SIZE), offset: String(offset) })

export const getDiagnostic = (mode: AdminMode, receiptId: string): Promise<DiagnosticDetail> =>
  get(`/api/admin/diagnostics/${encodeURIComponent(receiptId)}`, { mode })

export const getLogs = (mode: AdminMode, q: string, level: string, offset: number): Promise<Listing<LogEntry>> =>
  get('/api/admin/logs', { mode, q, level, limit: String(ADMIN_PAGE_SIZE), offset: String(offset) })

export const getLogGroups = async (mode: AdminMode): Promise<LogGroup[]> =>
  (await get<{ groups: LogGroup[] }>('/api/admin/logs/groups', { mode })).groups

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unit]}`
}

export function agoLabel(iso: string | null, now: number = Date.now()): string {
  if (!iso) return '아직 없음'
  const seconds = Math.max(0, Math.round((now - Date.parse(iso)) / 1000))
  if (Number.isNaN(seconds)) return iso
  if (seconds < 60) return `${seconds}초 전`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}분 전`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}시간 전`
  return `${Math.floor(seconds / 86400)}일 전`
}
