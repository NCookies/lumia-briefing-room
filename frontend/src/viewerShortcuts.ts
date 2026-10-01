import { VOLUME_STEP } from './volume.ts'

export const SEEK_STEP_SEC = 5
const VOLUME_PERCENT = Math.round(VOLUME_STEP * 100)

export type ViewerAction =
  | 'togglePlay'
  | 'seekBack'
  | 'seekForward'
  | 'nextClip'
  | 'addSection'
  | 'fullscreen'
  | 'volumeUp'
  | 'volumeDown'
  | 'prevClip'
  | 'archivePopup'
  | 'deleteClip'
  | 'markStart'
  | 'markEnd'
  | 'undo'
  | 'redo'
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
  { action: 'fullscreen', combos: [{ key: 'f' }], desc: '전체화면', group: '재생' },
  { action: 'volumeUp', combos: [{ key: 'ArrowUp' }], desc: `볼륨 ${VOLUME_PERCENT}% 올리기`, group: '재생' },
  { action: 'volumeDown', combos: [{ key: 'ArrowDown' }], desc: `볼륨 ${VOLUME_PERCENT}% 내리기`, group: '재생' },
  { action: 'seekBack', combos: [{ key: 'ArrowLeft' }], desc: `${SEEK_STEP_SEC}초 뒤로`, group: '재생' },
  { action: 'seekForward', combos: [{ key: 'ArrowRight' }], desc: `${SEEK_STEP_SEC}초 앞으로`, group: '재생' },
  { action: 'prevClip', combos: [{ key: 'ArrowLeft', ctrl: true }], desc: '이전 클립', group: '이동' },
  { action: 'nextClip', combos: [{ key: 'ArrowRight', ctrl: true }], desc: '다음 클립', group: '이동' },
  { action: 'markStart', combos: [{ key: 'i' }], desc: '선택한 클립의 시작을 지금 위치로', group: '범위 편집' },
  { action: 'addSection', combos: [{ key: 'n' }], desc: '구간 추가', group: '범위 편집' },
  { action: 'markEnd', combos: [{ key: 'o' }], desc: '선택한 클립의 끝을 지금 위치로', group: '범위 편집' },
  { action: 'undo', combos: [{ key: 'z', ctrl: true }], desc: '실행 취소', group: '범위 편집' },
  { action: 'redo', combos: [{ key: 'y', ctrl: true }], desc: '다시 시도', group: '범위 편집' },
  { action: 'archivePopup', combos: [{ key: 's', ctrl: true }], desc: '보관', group: '선택한 클립' },
  { action: 'deleteClip', combos: [{ key: 'Delete' }], desc: '삭제', group: '선택한 클립' },
  { action: 'memo', combos: [{ key: 'm' }], desc: '메모', group: '선택한 클립' },
  { action: 'help', combos: [{ key: '?' }], desc: '단축키', group: '도움말' },
]

const KEY_NAMES: Record<string, string> = { ' ': 'Space', ArrowLeft: '←', ArrowRight: '→', ArrowUp: '↑', ArrowDown: '↓' }

export function comboLabel(c: Combo): string {
  const name = KEY_NAMES[c.key] ?? (c.key.length === 1 ? c.key.toUpperCase() : c.key)
  return c.ctrl ? `Ctrl+${name}` : name
}

export interface ShortcutGroup {
  title: string
  rows: { keys: string; desc: string }[]
}

/** 안내 표. `only` 를 주면 그 동작의 키만(클립 재생 화면은 범위 편집 키가 없다). */
export function shortcutGroupsFor(only?: ViewerAction[]): ShortcutGroup[] {
  const groups: ShortcutGroup[] = []
  for (const s of VIEWER_SHORTCUTS) {
    if (only && !only.includes(s.action)) continue
    let g = groups.find((x) => x.title === s.group)
    if (!g) groups.push((g = { title: s.group, rows: [] }))
    g.rows.push({ keys: s.combos.map(comboLabel).join(' / '), desc: s.desc })
  }
  return groups
}

/** 안내 표(풀영상 화면의 `⌨` 패널과 사용 안내 가이드가 같이 쓴다). */
export const SHORTCUT_GROUPS: ShortcutGroup[] = shortcutGroupsFor()

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
const REPEATABLE = new Set<ViewerAction>(['seekBack', 'seekForward', 'volumeUp', 'volumeDown'])

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
