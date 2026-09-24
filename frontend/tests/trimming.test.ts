import assert from 'node:assert/strict'
import test from 'node:test'

import { clampRange, formatTime, initialRange, MIN_LENGTH } from '../src/trimming.ts'

test('clampRange moves the start handle but keeps at least the minimum length before the end', () => {
  assert.deepEqual(clampRange({ start: 2, end: 10 }, 'start', 4, 30), { start: 4, end: 10 })
  assert.deepEqual(clampRange({ start: 2, end: 10 }, 'start', 9.8, 30), { start: 10 - MIN_LENGTH, end: 10 })
  assert.deepEqual(clampRange({ start: 2, end: 10 }, 'start', -3, 30), { start: 0, end: 10 })
})

test('clampRange moves the end handle but keeps at least the minimum length after the start', () => {
  assert.deepEqual(clampRange({ start: 2, end: 10 }, 'end', 12, 30), { start: 2, end: 12 })
  assert.deepEqual(clampRange({ start: 2, end: 10 }, 'end', 2.2, 30), { start: 2, end: 2 + MIN_LENGTH })
  assert.deepEqual(clampRange({ start: 2, end: 10 }, 'end', 99, 30), { start: 2, end: 30 })
})

test('formatTime writes minutes, seconds and tenths', () => {
  assert.equal(formatTime(0), '0:00.0')
  assert.equal(formatTime(5.54), '0:05.5')
  assert.equal(formatTime(83.25), '1:23.3')
})

test('initialRange starts at the playhead so the start point is set to the current position', () => {
  assert.deepEqual(initialRange(12.4, 33), { start: 12.4, end: 33 })
  assert.deepEqual(initialRange(0, 33), { start: 0, end: 33 })
})

test('initialRange falls back to the beginning when the playhead is at or near the end', () => {
  assert.deepEqual(initialRange(33, 33), { start: 0, end: 33 })
  assert.deepEqual(initialRange(32.5, 33), { start: 0, end: 33 })
  assert.deepEqual(initialRange(Number.NaN, 33), { start: 0, end: 33 })
})

import { addRange, clampRangeAt, removeRange, splitSummary } from '../src/trimming.ts'

test('addRange puts the new range in the free gap at the playhead and keeps ranges sorted', () => {
  const r = addRange([{ start: 0, end: 5 }], 8, 30)
  assert.deepEqual(r, { ranges: [{ start: 0, end: 5 }, { start: 8, end: 30 }], index: 1 })
})

test('addRange stops at the next range and falls back to the first free gap when the playhead is on a range', () => {
  assert.deepEqual(addRange([{ start: 10, end: 20 }], 2, 30), {
    ranges: [{ start: 2, end: 10 }, { start: 10, end: 20 }],
    index: 0,
  })
  assert.deepEqual(addRange([{ start: 0, end: 20 }], 5, 30), {
    ranges: [{ start: 0, end: 20 }, { start: 20, end: 30 }],
    index: 1,
  })
})

test('addRange returns null when no free gap is at least the minimum length', () => {
  assert.equal(addRange([{ start: 0, end: 30 }], 5, 30), null)
  assert.equal(addRange([{ start: 0, end: 10 }, { start: 10.5, end: 30 }], 5, 30), null)
})

test('clampRangeAt cannot cross neighbours', () => {
  const ranges = [{ start: 0, end: 5 }, { start: 10, end: 15 }, { start: 20, end: 25 }]
  assert.deepEqual(clampRangeAt(ranges, 1, 'start', 2, 30)[1], { start: 5, end: 15 })
  assert.deepEqual(clampRangeAt(ranges, 1, 'end', 28, 30)[1], { start: 10, end: 20 })
  assert.deepEqual(clampRangeAt(ranges, 1, 'start', 12, 30)[1], { start: 12, end: 15 })
  assert.deepEqual(clampRangeAt(ranges, 0, 'start', -4, 30)[0], { start: 0, end: 5 })
})

test('removeRange drops one range', () => {
  assert.deepEqual(removeRange([{ start: 0, end: 5 }, { start: 6, end: 9 }], 0), [{ start: 6, end: 9 }])
})

test('splitSummary totals the kept and removed seconds', () => {
  assert.deepEqual(splitSummary([{ start: 0, end: 5 }, { start: 10, end: 14 }], 30), { count: 2, kept: 9, removed: 21 })
})
