import assert from 'node:assert/strict'
import test from 'node:test'

import { fillHeight } from '../src/fillHeight.ts'

test('창 아래 여백만 남기고 남은 높이를 모두 쓴다', () => {
  assert.equal(fillHeight({ top: 100, viewportHeight: 900, bottomGap: 16, min: 460 }), 784)
})

test('남은 높이가 최소보다 작으면 최소 높이를 쓴다', () => {
  assert.equal(fillHeight({ top: 300, viewportHeight: 600, bottomGap: 16, min: 460 }), 460)
})

test('소수 좌표는 내림해 1px 넘쳐 스크롤이 생기지 않게 한다', () => {
  assert.equal(fillHeight({ top: 100.6, viewportHeight: 900, bottomGap: 16, min: 460 }), 783)
})
