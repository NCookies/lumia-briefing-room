export interface TelemetryStatus {
  installId: string
  displayId: string
  sendLabels: boolean
  sendLogs: boolean
  endpointConfigured: boolean
  mode: 'dev' | 'release'
  canSendInThisMode: boolean
  pendingLabels: number
  pendingLogs: number
  lastLabelsSentAt: number | null
  lastLogsSentAt: number | null
  lastDiagnosticReceipt: string | null
  lastDiagnosticAt: number | null
}

export interface TelemetryPreview {
  labels: { count: number; items: Record<string, unknown>[] }
  logs: { count: number; env: Record<string, unknown>; items: Record<string, unknown>[] }
  mode: 'dev' | 'release'
}

export function sendStateText(status: TelemetryStatus): string {
  if (!status.sendLabels && !status.sendLogs) return '전송이 꺼져 있습니다. 아무것도 보내지 않습니다.'
  if (!status.endpointConfigured) return '이 빌드에는 서버 연결 정보가 없어 보내지 않습니다.'
  if (!status.canSendInThisMode) return '개발 모드에서는 보내지 않습니다.'
  return '켜져 있습니다. 하루에 한 번 묶어서 보냅니다.'
}

const pad = (n: number) => String(n).padStart(2, '0')

export function formatSentAt(epochSeconds: number | null): string {
  if (epochSeconds === null) return '아직 보낸 적 없음'
  const d = new Date(epochSeconds * 1000)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export const pendingText = (count: number, noun: string): string =>
  count === 0 ? `보낼 ${noun} 없음` : `보낼 ${noun} ${count}건`

export type PrivacyBlock =
  | { type: 'h1' | 'h2' | 'p' | 'note'; text: string }
  | { type: 'list'; items: string[] }
  | { type: 'table'; header: string[]; rows: string[][] }

const splitRow = (line: string): string[] =>
  line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim())

const isSeparator = (line: string): boolean => /^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$/.test(line.trim())

/** docs/privacy.md 를 화면에 그릴 만큼만 해석한다(제목·인용·목록·표·문단). */
export function parsePrivacy(markdown: string): PrivacyBlock[] {
  const blocks: PrivacyBlock[] = []
  const lines = markdown.replace(/\r\n/g, '\n').split('\n')
  let paragraph: string[] = []
  let list: string[] = []

  const flush = () => {
    if (paragraph.length > 0) blocks.push({ type: 'p', text: paragraph.join(' ') })
    if (list.length > 0) blocks.push({ type: 'list', items: list })
    paragraph = []
    list = []
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const trimmed = line.trim()
    if (trimmed === '') {
      flush()
    } else if (trimmed.startsWith('# ')) {
      flush()
      blocks.push({ type: 'h1', text: trimmed.slice(2) })
    } else if (trimmed.startsWith('## ')) {
      flush()
      blocks.push({ type: 'h2', text: trimmed.slice(3) })
    } else if (trimmed.startsWith('> ')) {
      flush()
      blocks.push({ type: 'note', text: trimmed.slice(2) })
    } else if (trimmed.startsWith('|')) {
      flush()
      const header = splitRow(trimmed)
      const rows: string[][] = []
      let j = i + 1
      if (j < lines.length && isSeparator(lines[j])) j++
      while (j < lines.length && lines[j].trim().startsWith('|')) {
        rows.push(splitRow(lines[j]))
        j++
      }
      blocks.push({ type: 'table', header, rows })
      i = j - 1
    } else if (trimmed.startsWith('- ')) {
      if (paragraph.length > 0) flush()
      list.push(trimmed.slice(2))
    } else {
      if (list.length > 0) flush()
      paragraph.push(trimmed)
    }
  }
  flush()
  return blocks
}

export interface InlinePart {
  text: string
  bold: boolean
}

export function parseInlineBold(text: string): InlinePart[] {
  const parts: InlinePart[] = []
  const pattern = /\*\*(.+?)\*\*/g
  let last = 0
  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0
    if (index > last) parts.push({ text: text.slice(last, index), bold: false })
    parts.push({ text: match[1], bold: true })
    last = index + match[0].length
  }
  if (last < text.length) parts.push({ text: text.slice(last), bold: false })
  return parts
}

export interface DiagnosticsPreview {
  displayId: string
  mode: 'dev' | 'release'
  env: Record<string, unknown>
  count: number
  items: Record<string, unknown>[]
  endpointConfigured: boolean
  canSend: boolean
}

export interface DiagnosticsResult {
  ok: boolean
  receiptId: string | null
  saved: number
}

export function diagnosticsSummary(preview: DiagnosticsPreview): string {
  const parts = [
    preview.count === 0 ? '오류 기록 없음' : `오류 기록 ${preview.count}건`,
    `환경 정보 ${Object.keys(preview.env).length}항목`,
  ]
  if ('readFailStats' in preview.env) parts.push('판독 실패 통계 포함')
  return parts.join(' · ')
}

export const receiptShareText = (receipt: string | null, displayId: string): string =>
  receipt ? `접수 번호 ${receipt} (설치 ID ${displayId})` : `설치 ID ${displayId}`

export const DISPLAY_ID_NOTICE =
  '커뮤니티 등에 이 ID 를 알리면 이 ID 로 보낸 데이터가 본인과 연결될 수 있습니다. 프로그램을 다시 설치하거나 설정 폴더를 지우면 새 ID 가 만들어집니다. ' +
  '보낸 데이터를 지우는 요청은 이 짧은 ID 가 아니라 위의 전체 설치 식별자로만 합니다.'
