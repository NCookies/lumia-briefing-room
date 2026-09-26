import assert from 'node:assert/strict'
import test from 'node:test'

import { barWidths, pageRange } from '../src/adminApi.ts'

test('페이지 범위를 표시한다', () => {
  assert.equal(pageRange(0, 0), '결과 없음')
  assert.equal(pageRange(0, 120), '1–50 / 120')
  assert.equal(pageRange(100, 120), '101–120 / 120')
})

test('막대 너비는 최댓값 기준 백분율이다', () => {
  assert.deepEqual(barWidths({ a: 4, b: 2 }), [
    ['a', 4, 100],
    ['b', 2, 50],
  ])
  assert.deepEqual(barWidths({}), [])
})

import { agoLabel, formatBytes } from '../src/adminApi.ts'

test('용량을 읽기 좋게 표시한다', () => {
  assert.equal(formatBytes(512), '512 B')
  assert.equal(formatBytes(1536), '1.5 KB')
  assert.equal(formatBytes(5 * 1024 * 1024), '5.0 MB')
  assert.equal(formatBytes(300 * 1024 * 1024 * 1024), '300 GB')
})

test('마지막 수신 시각을 "몇 분 전"으로 표시한다', () => {
  const now = Date.parse('2026-09-26T12:00:00Z')
  assert.equal(agoLabel(null, now), '아직 없음')
  assert.equal(agoLabel('2026-09-26T11:59:30Z', now), '30초 전')
  assert.equal(agoLabel('2026-09-26T11:55:00Z', now), '5분 전')
  assert.equal(agoLabel('2026-09-26T09:00:00Z', now), '3시간 전')
  assert.equal(agoLabel('2026-09-24T12:00:00Z', now), '2일 전')
})
