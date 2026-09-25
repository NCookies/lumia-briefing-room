import assert from 'node:assert/strict'
import test from 'node:test'

import { activityLabels, shouldRefresh } from '../src/activity.ts'

const task = (label: string, startedAt = 1) => ({ id: startedAt, kind: 'watch', label, startedAt })

test('lists refresh every interval while work is running', () => {
  assert.equal(shouldRefresh({ wasBusy: true, busy: true, msSinceRefresh: 5000, intervalMs: 5000 }), true)
  assert.equal(shouldRefresh({ wasBusy: true, busy: true, msSinceRefresh: 4999, intervalMs: 5000 }), false)
})

test('lists refresh once right when the work finishes', () => {
  assert.equal(shouldRefresh({ wasBusy: true, busy: false, msSinceRefresh: 100, intervalMs: 5000 }), true)
})

test('nothing refreshes while idle', () => {
  assert.equal(shouldRefresh({ wasBusy: false, busy: false, msSinceRefresh: 999999, intervalMs: 5000 }), false)
})

test('a task that just started refreshes at the next interval, not immediately', () => {
  assert.equal(shouldRefresh({ wasBusy: false, busy: true, msSinceRefresh: 100, intervalMs: 5000 }), false)
})

test('labels merge server tasks and the backfill progress', () => {
  assert.deepEqual(activityLabels([task('게임 분석 중 (09/24 15:55 시작)')], null), ['게임 분석 중 (09/24 15:55 시작)'])
  assert.deepEqual(activityLabels([], '과거 녹화 분석 중 42%'), ['과거 녹화 분석 중 42%'])
  assert.deepEqual(activityLabels([task('a', 1), task('b', 2)], '과거 녹화 분석 중 1%'), ['a', 'b', '과거 녹화 분석 중 1%'])
  assert.deepEqual(activityLabels([], null), [])
})
