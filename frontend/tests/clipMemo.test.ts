import assert from 'node:assert/strict'
import test from 'node:test'

import { CLIP_MEMO_MAX, clampMemo, memoToSave } from '../src/clipMemo.ts'

test('메모는 5,000자까지', () => {
  assert.equal(CLIP_MEMO_MAX, 5000)
  assert.equal(clampMemo('가'.repeat(6000)).length, 5000)
  assert.equal(clampMemo('짧다'), '짧다')
})

test('바뀐 게 없으면 저장하지 않고, 비우면 null 로 지운다', () => {
  assert.equal(memoToSave('같은 메모', '같은 메모'), undefined)
  assert.equal(memoToSave('  같은 메모  ', '같은 메모'), undefined)
  assert.equal(memoToSave('새 메모', null), '새 메모')
  assert.equal(memoToSave('   ', '있던 메모'), null)
  assert.equal(memoToSave('', undefined), undefined)
})
