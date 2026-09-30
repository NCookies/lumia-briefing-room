import assert from 'node:assert/strict'
import test from 'node:test'

import { canDropOn, childRel, dragItems, nameOfRel, parentRel, selectionSummary, toggle } from '../src/library.ts'

test('parentRel and nameOfRel split slash paths', () => {
  assert.equal(parentRel('a/b/c.mp4'), 'a/b')
  assert.equal(parentRel('a'), '')
  assert.equal(parentRel(''), '')
  assert.equal(nameOfRel('a/b/c.mp4'), 'c.mp4')
  assert.equal(childRel('', 'x'), 'x')
  assert.equal(childRel('a/b', 'x'), 'a/b/x')
})

test('toggle adds and removes without mutating', () => {
  const a = new Set<string>()
  const b = toggle(a, 'x')
  assert.equal(a.size, 0)
  assert.deepEqual([...b], ['x'])
  assert.deepEqual([...toggle(b, 'x')], [])
})

test('dragItems drags the whole selection when the dragged item is selected', () => {
  assert.deepEqual(dragItems(new Set(['a', 'b']), 'a'), ['a', 'b'])
  assert.deepEqual(dragItems(new Set(['a', 'b']), 'c'), ['c'])
  assert.deepEqual(dragItems(new Set(), 'c'), ['c'])
})

test('canDropOn refuses the same parent, itself and its own children', () => {
  assert.equal(canDropOn(['a/x.mp4'], 'b'), true)
  assert.equal(canDropOn(['a/x.mp4'], 'a'), false, '이미 그 폴더에 있다')
  assert.equal(canDropOn(['a'], 'a'), false)
  assert.equal(canDropOn(['a'], 'a/inner'), false)
  assert.equal(canDropOn(['a', 'b/x.mp4'], 'c'), true)
  assert.equal(canDropOn(['ab'], 'a'), true, '이름이 접두만 같은 폴더는 안쪽이 아니다')
  assert.equal(canDropOn([], 'a'), false)
})

test('selectionSummary counts folders and clips separately', () => {
  assert.equal(selectionSummary(['a', 'c'], ['b/x.mp4'], new Set(['a', 'c'])), '폴더 2개')
  assert.equal(selectionSummary(['a', 'c'], ['b/x.mp4'], new Set(['a', 'b/x.mp4'])), '폴더 1개 · 클립 1개')
  assert.equal(selectionSummary([], ['v1.2'], new Set(['v1.2'])), '클립 1개')
  assert.equal(selectionSummary([], [], new Set()), '')
})

test('canDropOn refuses the whole drop if any item would go into itself', () => {
  assert.equal(canDropOn(['a', 'b/x.mp4'], 'a/inner'), false)
  assert.equal(canDropOn(['a/x.mp4', 'c/y.mp4'], 'a'), true, '하나는 이미 있지만 다른 하나는 옮길 수 있다')
})
