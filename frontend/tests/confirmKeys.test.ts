import assert from 'node:assert/strict'
import test from 'node:test'

import { confirmKeyAction } from '../src/confirmKeys.ts'

test('Esc 는 어디에 포커스가 있든 취소다', () => {
  for (const focus of ['cancel', 'confirm', 'other'] as const) assert.deepEqual(confirmKeyAction('Escape', focus), { kind: 'cancel' })
})

test('←/→ 는 취소/확인 버튼 사이로 포커스를 옮긴다', () => {
  assert.deepEqual(confirmKeyAction('ArrowLeft', 'confirm'), { kind: 'focus', to: 'cancel' })
  assert.deepEqual(confirmKeyAction('ArrowRight', 'cancel'), { kind: 'focus', to: 'confirm' })
  assert.deepEqual(confirmKeyAction('ArrowRight', 'other'), { kind: 'focus', to: 'confirm' })
})

test('Space·Enter 는 포커스가 있는 버튼을 누른다', () => {
  for (const key of [' ', 'Enter']) {
    assert.deepEqual(confirmKeyAction(key, 'cancel'), { kind: 'cancel' })
    assert.deepEqual(confirmKeyAction(key, 'confirm'), { kind: 'confirm' })
  }
})

test('버튼이 아닌 곳(체크박스 등)에서는 Enter 가 확인, Space 는 원래 동작(체크 토글)', () => {
  assert.deepEqual(confirmKeyAction('Enter', 'other'), { kind: 'confirm' })
  assert.deepEqual(confirmKeyAction(' ', 'other'), { kind: 'native' })
})

test('Tab 은 건드리지 않고, 나머지 키는 뒤 화면으로 새지 않게 삼킨다', () => {
  assert.deepEqual(confirmKeyAction('Tab', 'confirm'), { kind: 'pass' })
  assert.deepEqual(confirmKeyAction('Delete', 'confirm'), { kind: 'swallow' })
  assert.deepEqual(confirmKeyAction('n', 'cancel'), { kind: 'swallow' })
})

test('Space·Enter 를 꾹 눌러 생기는 반복 입력은 삼킨다(창이 닫힌 뒤 뒤 화면에 새지 않게)', () => {
  assert.deepEqual(confirmKeyAction(' ', 'confirm', true), { kind: 'swallow' })
  assert.deepEqual(confirmKeyAction('Enter', 'cancel', true), { kind: 'swallow' })
})
