import assert from 'node:assert/strict'
import test from 'node:test'

import { describeCleanup, formatBytes, parseLimit } from '../src/retention.ts'

test('parseLimit turns blank or invalid text into null (no limit)', () => {
  assert.equal(parseLimit(''), null)
  assert.equal(parseLimit('  '), null)
  assert.equal(parseLimit('abc'), null)
  assert.equal(parseLimit('0'), null)
  assert.equal(parseLimit('-3'), null)
})

test('parseLimit reads positive numbers, decimals included', () => {
  assert.equal(parseLimit('30'), 30)
  assert.equal(parseLimit(' 12.5 '), 12.5)
})

test('formatBytes picks a readable unit', () => {
  assert.equal(formatBytes(0), '0 B')
  assert.equal(formatBytes(1536), '1.5 KB')
  assert.equal(formatBytes(5 * 1024 ** 2), '5.0 MB')
  assert.equal(formatBytes(3.25 * 1024 ** 3), '3.25 GB')
})

test('describeCleanup summarizes what a run would do', () => {
  assert.equal(
    describeCleanup({ toDelete: 3, bytesToFree: 1024 ** 3, applied: false }),
    '3개 삭제 · 1.00 GB',
  )
  assert.equal(describeCleanup({ toDelete: 0, bytesToFree: 0, applied: false }), '정리할 항목이 없습니다')
})

test('describeCleanup mentions clips kept before deleting and videos held back', () => {
  const base = { bytesToFree: 2 * 1024 ** 3, applied: true }
  assert.equal(
    describeCleanup({ ...base, toDelete: 2, preserveClips: 3, heldBack: 0 }),
    '2개 삭제 · 2.00 GB · 지우기 전에 클립 3개를 남깁니다',
  )
  assert.equal(
    describeCleanup({ ...base, toDelete: 1, preserveClips: 0, heldBack: 1 }),
    '1개 삭제 · 2.00 GB · 클립을 남기지 못한 1개는 지우지 않았습니다',
  )
  assert.equal(describeCleanup({ ...base, toDelete: 0, preserveClips: 0, heldBack: 2 }), '클립을 남기지 못한 2개는 지우지 않았습니다')
  assert.equal(describeCleanup({ ...base, toDelete: 0 }), '정리할 항목이 없습니다')
})
