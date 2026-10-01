export const SEEK_STEP_SEC = 5

export type ViewerAction =
  | 'togglePlay'
  | 'seekBack'
  | 'seekForward'
  | 'nextClip'
  | 'prevClip'
  | 'archive'
  | 'archivePopup'
  | 'dismiss'
  | 'deleteClip'
  | 'markStart'
  | 'markEnd'
  | 'undo'
  | 'memo'
  | 'help'

export interface Combo {
  /** `' '`·`ArrowLeft`·`Delete`·`?` 이거나 소문자 한 글자. */
  key: string
  ctrl?: boolean
}

export interface Shortcut {
  action: ViewerAction
  combos: Combo[]
  desc: string
  group: string
}

/** 풀영상 화면 단축키의 유일한 정의. 키 판정(`decideKey`)과 안내 표(`SHORTCUT_GROUPS`)가 둘 다 이걸 쓴다. */
export const VIEWER_SHORTCUTS: Shortcut[] = [
  { action: 'togglePlay', combos: [{ key: ' ' }], desc: '재생 / 일시정지', group: '재생' },
  { action: 'seekBack', combos: [{ key: 'ArrowLeft' }], desc: `${SEEK_STEP_SEC}초 뒤로`, group: '재생' },
  { action: 'seekForward', combos: [{ key: 'ArrowRight' }], desc: `${SEEK_STEP_SEC}초 앞으로`, group: '재생' },
  { action: 'prevClip', combos: [{ key: 'p' }, { key: 'ArrowLeft', ctrl: true }], desc: '이전 클립(현재 클립 시작 후 3초 안이면 바로 그 앞 클립)', group: '이동' },
  { action: 'nextClip', combos: [{ key: 'n' }, { key: 'ArrowRight', ctrl: true }], desc: '다음 클립', group: '이동' },
  { action: 'markStart', combos: [{ key: 'i' }], desc: '선택한 클립의 시작을 지금 위치로', group: '범위 편집' },
  { action: 'markEnd', combos: [{ key: 'o' }], desc: '선택한 클립의 끝을 지금 위치로', group: '범위 편집' },
  { action: 'undo', combos: [{ key: 'z', ctrl: true }], desc: '되돌리기', group: '범위 편집' },
  { action: 'archive', combos: [{ key: 's' }], desc: '선택한 클립 보관(보관한 클립은 고친 범위 다시 저장)', group: '선택한 클립' },
  { action: 'archivePopup', combos: [{ key: 's', ctrl: true }], desc: '보관 위치 고르기(보관한 클립의 범위를 고쳤으면 먼저 저장)', group: '선택한 클립' },
  { action: 'dismiss', combos: [{ key: 'd' }], desc: '무시(직접 추가한 구간은 삭제)', group: '선택한 클립' },
  { action: 'deleteClip', combos: [{ key: 'Delete' }], desc: '클립 삭제(클립이 없으면 D 와 같음)', group: '선택한 클립' },
  { action: 'memo', combos: [{ key: 'm' }], desc: '메모 열기(보관한 클립)', group: '선택한 클립' },
  { action: 'help', combos: [{ key: '?' }], desc: '이 표 보기·닫기', group: '도움말' },
]

/** 창 안에서만 먹는 키. 판정은 각 창이 하고 표시만 여기서 한다. */
export const WINDOW_HINTS: { keys: string; desc: string }[] = [
  { keys: '↑ / ↓ · Enter · Esc', desc: '보관 위치 창: 칸 옮기기 · 보관 · 닫기' },
  { keys: '← / → · Space·Enter · Esc', desc: '확인 창: 취소/확인 사이 옮기기 · 누르기 · 취소' },
  { keys: 'Ctrl+Enter', desc: '메모: 저장하고 닫기' },
]

const KEY_NAMES: Record<string, string> = { ' ': 'Space', ArrowLeft: '←', ArrowRight: '→' }

export function comboLabel(c: Combo): string {
  const name = KEY_NAMES[c.key] ?? (c.key.length === 1 ? c.key.toUpperCase() : c.key)
  return c.ctrl ? `Ctrl+${name}` : name
}

export interface ShortcutGroup {
  title: string
  rows: { keys: string; desc: string }[]
}

function buildGroups(): ShortcutGroup[] {
  const groups: ShortcutGroup[] = []
  for (const s of VIEWER_SHORTCUTS) {
    let g = groups.find((x) => x.title === s.group)
    if (!g) groups.push((g = { title: s.group, rows: [] }))
    g.rows.push({ keys: s.combos.map(comboLabel).join(' / '), desc: s.desc })
  }
  groups.push({ title: '창 안에서', rows: WINDOW_HINTS })
  return groups
}

/** 안내 표(풀영상 화면의 `⌨` 패널과 사용 안내 가이드가 같이 쓴다). */
export const SHORTCUT_GROUPS: ShortcutGroup[] = buildGroups()

export interface TargetInfo {
  tag: string
  type?: string
  editable?: boolean
}

const NON_TEXT_INPUTS = new Set(['checkbox', 'radio', 'range', 'button', 'submit', 'reset', 'file', 'color', 'image'])

/** 글자를 치는 칸인가. 체크박스·슬라이더·버튼은 아니다 — 이들에 포커스가 있어도 단축키는 먹어야 한다. */
export function isTextEntry(t: TargetInfo | null): boolean {
  if (!t) return false
  if (t.editable) return true
  if (t.tag === 'TEXTAREA' || t.tag === 'SELECT') return true
  if (t.tag === 'INPUT') return !NON_TEXT_INPUTS.has((t.type ?? 'text').toLowerCase())
  return false
}

export interface KeyInput {
  key: string
  code: string
  ctrl: boolean
  meta: boolean
  alt: boolean
  shift: boolean
  repeat: boolean
  textEntry: boolean
  /** 확인 창·팝업·메뉴 등이 떠 있다. */
  modalOpen: boolean
}

export interface KeyDecision {
  action: ViewerAction | null
  preventDefault: boolean
}

const NONE: KeyDecision = { action: null, preventDefault: false }
const REPEATABLE = new Set<ViewerAction>(['seekBack', 'seekForward'])

/** 한글 자판이면 `key` 가 `ㅜ` 라 물리 키(`code`)로 글자를 정한다. */
function normalizeKey(k: Pick<KeyInput, 'key' | 'code'>): string {
  const m = /^Key([A-Z])$/.exec(k.code)
  if (m) return m[1].toLowerCase()
  return k.key.length === 1 ? k.key.toLowerCase() : k.key
}

export function decideKey(k: KeyInput): KeyDecision {
  const key = normalizeKey(k)
  const ctrl = k.ctrl || k.meta
  if (ctrl && key === 's') {
    const open = !k.textEntry && !k.modalOpen && !k.repeat
    return { action: open ? 'archivePopup' : null, preventDefault: true }
  }
  if (k.modalOpen || k.textEntry || k.alt) return NONE
  if (ctrl && k.shift) return NONE
  const row = VIEWER_SHORTCUTS.find((s) => s.combos.some((c) => c.key === key && (c.ctrl === true) === ctrl))
  if (!row) return NONE
  if (k.repeat && !REPEATABLE.has(row.action)) return { action: null, preventDefault: true }
  return { action: row.action, preventDefault: true }
}

const HELP_KEY = 'lumia.viewer.shortcutHelpSeen'

export function loadHelpSeen(): boolean {
  try {
    return localStorage.getItem(HELP_KEY) === '1'
  } catch {
    return false
  }
}

export function saveHelpSeen(): void {
  try {
    localStorage.setItem(HELP_KEY, '1')
  } catch {
    // 저장 실패는 무시한다
  }
}
