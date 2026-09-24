import assert from 'node:assert/strict'
import test from 'node:test'

import { buildPhaseColumns, phaseLabel } from '../src/timeline.ts'

test('phaseLabel counts days from 1 with day then night', () => {
  assert.equal(phaseLabel(0), '1일차 낮')
  assert.equal(phaseLabel(1), '1일차 밤')
  assert.equal(phaseLabel(4), '3일차 낮')
})

test('buildPhaseColumns keeps empty phases between the first phase and the last clip', () => {
  const cols = buildPhaseColumns([
    { id: 'a', phaseIndex: 1 },
    { id: 'b', phaseIndex: 4 },
    { id: 'c', phaseIndex: 4 },
  ])
  assert.deepEqual(
    cols.map((c) => [c.phaseIndex, c.clips.length]),
    [[0, 0], [1, 1], [2, 0], [3, 0], [4, 2]],
  )
})

test('buildPhaseColumns marks the free revive zone up to phase 3 and the credit zone after it', () => {
  const cols = buildPhaseColumns([{ phaseIndex: 4 }])
  assert.deepEqual(cols.map((c) => c.zone), ['free', 'free', 'free', 'free', 'credit'])
})

test('buildPhaseColumns puts clips without a phase in a trailing unknown column', () => {
  const cols = buildPhaseColumns([{ phaseIndex: null }, { phaseIndex: 0 }])
  assert.deepEqual(cols.map((c) => c.label), ['1일차 낮', '시점 알 수 없음'])
  assert.equal(cols[1].zone, null)
  assert.equal(buildPhaseColumns([{ phaseIndex: null }]).length, 1)
  assert.deepEqual(buildPhaseColumns([]), [])
})
