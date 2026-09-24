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
    describeCleanup({ toTrash: 3, toPurge: 2, bytesToFree: 1024 ** 3, applied: false }),
    '휴지통으로 이동 3개 · 완전 삭제 2개 · 1.00 GB',
  )
  assert.equal(describeCleanup({ toTrash: 0, toPurge: 0, bytesToFree: 0, applied: false }), '정리할 항목이 없습니다')
})
