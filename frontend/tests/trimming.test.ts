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
