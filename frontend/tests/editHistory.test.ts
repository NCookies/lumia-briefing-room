import assert from 'node:assert/strict'
import test from 'node:test'

import { EMPTY_HISTORY, pushEdit, redoStep, remapId, undoStep, type Edit } from '../src/editHistory.ts'

const range = (id: string, prev: [number, number], next: [number, number]): Edit => ({ kind: 'range', id, prev, next })

test('되돌리면 되돌린 편집이 다시 실행 쪽으로 넘어간다', () => {
  const a = range('a', [1, 2], [3, 4])
  const b: Edit = { kind: 'dismiss', id: 'b' }
  let h = pushEdit(pushEdit(EMPTY_HISTORY, a), b)
  const u1 = undoStep(h)!
  assert.deepEqual(u1.edit, b)
  h = u1.history
  assert.deepEqual(h.undo, [a])
  assert.deepEqual(h.redo, [b])
  const r1 = redoStep(h)!
  assert.deepEqual(r1.edit, b)
  assert.deepEqual(r1.history.undo, [a, b])
  assert.deepEqual(r1.history.redo, [])
})

test('되돌릴 것·다시 실행할 것이 없으면 null', () => {
  assert.equal(undoStep(EMPTY_HISTORY), null)
  assert.equal(redoStep(EMPTY_HISTORY), null)
})

test('새 편집을 하면 다시 실행 기록은 사라진다', () => {
  const a = range('a', [1, 2], [3, 4])
  const h = undoStep(pushEdit(EMPTY_HISTORY, a))!.history
  assert.equal(h.redo.length, 1)
  assert.deepEqual(pushEdit(h, range('b', [0, 1], [0, 2])).redo, [])
})

test('여러 번 되돌리고 같은 순서로 다시 실행한다', () => {
  const a = range('a', [1, 2], [3, 4])
  const b = range('a', [3, 4], [5, 6])
  let h = pushEdit(pushEdit(EMPTY_HISTORY, a), b)
  h = undoStep(undoStep(h)!.history)!.history
  assert.deepEqual(redoStep(h)!.edit, a)
  assert.deepEqual(redoStep(redoStep(h)!.history)!.edit, b)
})

test('다시 추가한 구간의 새 id 로 양쪽 기록의 옛 id 를 바꾼다', () => {
  const add: Edit = { kind: 'add', id: 'u1', range: [10, 20] }
  const edit = range('u1', [10, 20], [12, 22])
  const h = remapId({ undo: [add], redo: [edit, { kind: 'dismiss', id: 'other' }] }, 'u1', 'u2')
  assert.deepEqual(h.undo, [{ kind: 'add', id: 'u2', range: [10, 20] }])
  assert.deepEqual(h.redo, [range('u2', [10, 20], [12, 22]), { kind: 'dismiss', id: 'other' }])
})
