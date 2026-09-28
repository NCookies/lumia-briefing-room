import assert from 'node:assert/strict'
import test from 'node:test'

import {
  deleteConfirmMessage,
  needsPermanentSkipWarning,
  resolveDeleteChoice,
  type DeleteMode,
} from '../src/deleteConfirm.ts'

test('recycle mode explains that restoring later needs every file', () => {
  const msg = deleteConfirmMessage('recycle')
  assert.match(msg, /Windows 휴지통/)
  assert.match(msg, /영상.*정보.*썸네일/)
})

test('permanent mode warns it cannot be undone', () => {
  const msg = deleteConfirmMessage('permanent')
  assert.match(msg, /되돌릴 수 없습니다/)
})

test('choosing permanent + skip next time needs one more warning', () => {
  assert.equal(needsPermanentSkipWarning({ skipNext: true, permanent: true }), true)
  assert.equal(needsPermanentSkipWarning({ skipNext: true, permanent: false }), false)
  assert.equal(needsPermanentSkipWarning({ skipNext: false, permanent: true }), false)
  assert.equal(needsPermanentSkipWarning({ skipNext: false, permanent: false }), false)
})

test('resolveDeleteChoice maps the permanent checkbox to a delete mode', () => {
  const asMode = (permanent: boolean): DeleteMode => resolveDeleteChoice({ skipNext: false, permanent }).mode
  assert.equal(asMode(true), 'permanent')
  assert.equal(asMode(false), 'recycle')
})

test('resolveDeleteChoice carries the skipNext flag through unchanged', () => {
  assert.equal(resolveDeleteChoice({ skipNext: true, permanent: false }).skipNext, true)
  assert.equal(resolveDeleteChoice({ skipNext: false, permanent: false }).skipNext, false)
})
