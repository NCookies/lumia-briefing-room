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
