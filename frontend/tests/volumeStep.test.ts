import assert from 'node:assert/strict'
import test from 'node:test'

import { VOLUME_STEP, stepVolume } from '../src/volume.ts'

test('볼륨은 5% 씩 오르내리고 부동소수점 오차가 쌓이지 않는다', () => {
  assert.equal(VOLUME_STEP, 0.05)
  let s = { volume: 0.5, muted: false }
  for (let i = 0; i < 3; i++) s = stepVolume(s, 1)
  assert.equal(s.volume, 0.65)
  for (let i = 0; i < 20; i++) s = stepVolume(s, -1)
  assert.equal(s.volume, 0)
})

test('0~1 범위를 벗어나지 않는다', () => {
  assert.equal(stepVolume({ volume: 1, muted: false }, 1).volume, 1)
  assert.equal(stepVolume({ volume: 0, muted: false }, -1).volume, 0)
})

test('음소거 중 볼륨을 올리면 음소거가 풀리고, 내리면 음소거는 그대로', () => {
  assert.deepEqual(stepVolume({ volume: 0.3, muted: true }, 1), { volume: 0.35, muted: false })
  assert.deepEqual(stepVolume({ volume: 0.3, muted: true }, -1), { volume: 0.25, muted: true })
})
