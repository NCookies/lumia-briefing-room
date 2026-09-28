import assert from 'node:assert/strict'
import test from 'node:test'

import {
  cleanupReasonLabel,
  cleanupReasonTooltip,
  gameCleanupEntry,
  type CleanupPreviewMap,
} from '../src/cleanupPreview.ts'

const NOW = new Date('2026-09-28T00:00:00Z')

test('age reason counts whole days remaining until dueAt', () => {
  assert.equal(cleanupReasonLabel({ reason: 'age', dueAt: '2026-10-01T00:00:00Z' }, NOW), '3일 후 삭제 예정')
})

test('age reason already past its dueAt says it is about to be deleted', () => {
  assert.equal(cleanupReasonLabel({ reason: 'age', dueAt: '2026-09-27T00:00:00Z' }, NOW), '곧 삭제 예정')
})

test('count and size reasons share the same generic label', () => {
  assert.equal(cleanupReasonLabel({ reason: 'count', dueAt: null }, NOW), '한도 초과로 삭제 예정')
  assert.equal(cleanupReasonLabel({ reason: 'size', dueAt: null }, NOW), '한도 초과로 삭제 예정')
})

test('only count/size reasons get the "current estimate" tooltip', () => {
  assert.equal(cleanupReasonTooltip({ reason: 'age', dueAt: '2026-10-01T00:00:00Z' }), undefined)
  assert.equal(typeof cleanupReasonTooltip({ reason: 'count', dueAt: null }), 'string')
})

test('game entry is null unless every clip in the game is pending deletion', () => {
  const preview: CleanupPreviewMap = { a: { reason: 'age', dueAt: '2026-10-01T00:00:00Z' } }
  assert.equal(gameCleanupEntry(['a', 'b'], preview), null)
  assert.equal(gameCleanupEntry([], preview), null)
})

test('game entry picks the soonest age-based reason among the game clips', () => {
  const preview: CleanupPreviewMap = {
    a: { reason: 'age', dueAt: '2026-10-05T00:00:00Z' },
    b: { reason: 'age', dueAt: '2026-10-01T00:00:00Z' },
  }
  assert.deepEqual(gameCleanupEntry(['a', 'b'], preview), { reason: 'age', dueAt: '2026-10-01T00:00:00Z' })
})

test('game entry falls back to a count/size reason when no clip has an age reason', () => {
  const preview: CleanupPreviewMap = {
    a: { reason: 'count', dueAt: null },
    b: { reason: 'count', dueAt: null },
  }
  assert.deepEqual(gameCleanupEntry(['a', 'b'], preview), { reason: 'count', dueAt: null })
})
