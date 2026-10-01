import assert from 'node:assert/strict'
import test from 'node:test'

import {
  SEEK_STEP_SEC,
  SHORTCUT_GROUPS,
  VIEWER_SHORTCUTS,
  comboLabel,
  decideKey,
  isTextEntry,
  type KeyInput,
  type ViewerAction,
} from '../src/viewerShortcuts.ts'

const press = (key: string, extra: Partial<KeyInput> = {}): KeyInput => ({
  key,
  code: '',
  ctrl: false,
  meta: false,
  alt: false,
  shift: false,
  repeat: false,
  textEntry: false,
  modalOpen: false,
  ...extra,
})

const action = (key: string, extra: Partial<KeyInput> = {}) => decideKey(press(key, extra)).action

test('기존 단축키는 그대로 풀린다', () => {
  assert.equal(action(' '), 'togglePlay')
  assert.equal(action('ArrowLeft'), 'seekBack')
  assert.equal(action('ArrowRight'), 'seekForward')
  assert.equal(action('n'), 'nextClip')
  assert.equal(action('p'), 'prevClip')
  assert.equal(action('s'), 'archive')
  assert.equal(action('d'), 'dismiss')
  assert.equal(action('i'), 'markStart')
  assert.equal(action('o'), 'markEnd')
  assert.equal(action('z', { ctrl: true }), 'undo')
})

test('Ctrl+Y 는 다시 실행이다(한글 자판 포함)', () => {
  assert.equal(action('y', { ctrl: true }), 'redo')
  assert.equal(action('ㅛ', { code: 'KeyY', ctrl: true }), 'redo')
  assert.equal(action('y'), null)
})

test('대문자(Shift·CapsLock)로 눌러도 같은 단축키다', () => {
  assert.equal(action('N'), 'nextClip')
  assert.equal(action('P', { shift: true }), 'prevClip')
})

test('한글 자판에서도 물리 키(code)로 푼다', () => {
  assert.equal(action('ㅜ', { code: 'KeyN' }), 'nextClip')
  assert.equal(action('ㅔ', { code: 'KeyP' }), 'prevClip')
  assert.equal(action('ㅋ', { code: 'KeyZ', ctrl: true }), 'undo')
})

test('Ctrl+←/→ 는 이전/다음 클립, Delete 는 클립 삭제, M 은 메모, ? 는 도움말', () => {
  assert.equal(action('ArrowLeft', { ctrl: true }), 'prevClip')
  assert.equal(action('ArrowRight', { ctrl: true }), 'nextClip')
  assert.equal(action('Delete'), 'deleteClip')
  assert.equal(action('m'), 'memo')
  assert.equal(action('?', { shift: true }), 'help')
})

test('Ctrl+S 는 보관 위치 팝업이고 브라우저 페이지 저장은 막는다', () => {
  assert.deepEqual(decideKey(press('s', { ctrl: true })), { action: 'archivePopup', preventDefault: true })
})

test('글자 입력칸 안에서는 단축키를 끄지만 Ctrl+S 의 페이지 저장 창은 막는다', () => {
  assert.deepEqual(decideKey(press(' ', { textEntry: true })), { action: null, preventDefault: false })
  assert.deepEqual(decideKey(press('s', { textEntry: true })), { action: null, preventDefault: false })
  assert.deepEqual(decideKey(press('ArrowLeft', { ctrl: true, textEntry: true })), { action: null, preventDefault: false })
  assert.deepEqual(decideKey(press('s', { ctrl: true, textEntry: true })), { action: null, preventDefault: true })
})

test('창·팝업·메뉴가 열려 있으면 아무 단축키도 먹지 않는다', () => {
  assert.deepEqual(decideKey(press(' ', { modalOpen: true })), { action: null, preventDefault: false })
  assert.deepEqual(decideKey(press('s', { ctrl: true, modalOpen: true })), { action: null, preventDefault: true })
})

test('Alt 조합과 Ctrl+Shift 조합, 모르는 키는 건드리지 않는다', () => {
  assert.deepEqual(decideKey(press('n', { alt: true })), { action: null, preventDefault: false })
  assert.deepEqual(decideKey(press('z', { ctrl: true, shift: true })), { action: null, preventDefault: false })
  assert.deepEqual(decideKey(press('ArrowLeft', { ctrl: true, shift: true })), { action: null, preventDefault: false })
  assert.deepEqual(decideKey(press('x')), { action: null, preventDefault: false })
  assert.deepEqual(decideKey(press('c', { ctrl: true })), { action: null, preventDefault: false })
})

test('꾹 누르면 ←/→ 만 반복하고 나머지는 한 번만 동작한다', () => {
  assert.equal(action('ArrowRight', { repeat: true }), 'seekForward')
  assert.deepEqual(decideKey(press(' ', { repeat: true })), { action: null, preventDefault: true })
  assert.deepEqual(decideKey(press('Delete', { repeat: true })), { action: null, preventDefault: true })
})

test('입력칸 판정: 체크박스·슬라이더·버튼은 글자 입력칸이 아니다', () => {
  assert.equal(isTextEntry({ tag: 'INPUT', type: 'checkbox' }), false)
  assert.equal(isTextEntry({ tag: 'INPUT', type: 'range' }), false)
  assert.equal(isTextEntry({ tag: 'BUTTON' }), false)
  assert.equal(isTextEntry({ tag: 'INPUT', type: 'text' }), true)
  assert.equal(isTextEntry({ tag: 'INPUT' }), true)
  assert.equal(isTextEntry({ tag: 'TEXTAREA' }), true)
  assert.equal(isTextEntry({ tag: 'SELECT' }), true)
  assert.equal(isTextEntry({ tag: 'DIV', editable: true }), true)
  assert.equal(isTextEntry(null), false)
})

test('안내 표의 모든 키가 표에 적힌 동작으로 풀린다(표와 판정이 한 정의를 쓴다)', () => {
  for (const row of VIEWER_SHORTCUTS) {
    for (const combo of row.combos) {
      const got: ViewerAction | null = decideKey(press(combo.key, { ctrl: combo.ctrl === true, shift: combo.key === '?' })).action
      assert.equal(got, row.action, `${comboLabel(combo)} → ${row.action}`)
    }
  }
})

test('키 이름 표기', () => {
  assert.equal(comboLabel({ key: ' ' }), 'Space')
  assert.equal(comboLabel({ key: 'ArrowLeft', ctrl: true }), 'Ctrl+←')
  assert.equal(comboLabel({ key: 's', ctrl: true }), 'Ctrl+S')
  assert.equal(comboLabel({ key: 'Delete' }), 'Delete')
  assert.equal(comboLabel({ key: '?' }), '?')
})

test('안내 표에는 새 단축키와 창 안의 키가 모두 있고 이동 간격이 코드 상수와 같다', () => {
  const text = SHORTCUT_GROUPS.flatMap((g) => g.rows.map((r) => `${r.keys} ${r.desc}`)).join('\n')
  for (const need of ['Space', 'Ctrl\\+←', 'Ctrl\\+→', 'Delete', 'Ctrl\\+S', 'M', 'Ctrl\\+Enter', 'Ctrl\\+Z', 'Ctrl\\+Y', 'Esc']) assert.match(text, new RegExp(need))
  assert.match(text, new RegExp(`${SEEK_STEP_SEC}초`))
})
