import assert from 'node:assert/strict'
import test from 'node:test'

import { playerWidthCss, shouldAutoAdvance, showEvidence } from '../src/playerLayout.ts'

test('the player leaves room for the label controls so nothing is cut off', () => {
  assert.equal(playerWidthCss({ labeling: false, trimming: false }), 'min(97vw, calc((100vh - 8.5rem) * 1.7778))')
  assert.equal(playerWidthCss({ labeling: true, trimming: false }), 'min(97vw, calc((100vh - 16rem) * 1.7778))')
  assert.equal(playerWidthCss({ labeling: false, trimming: true }), 'min(97vw, calc((100vh - 16.5rem) * 1.7778))')
  assert.equal(playerWidthCss({ labeling: true, trimming: true }), 'min(97vw, calc((100vh - 24rem) * 1.7778))')
})

test('only the developer build jumps to the next clip after labeling', () => {
  assert.equal(shouldAutoAdvance({ tuning: true }), true)
  assert.equal(shouldAutoAdvance({ tuning: false }), false)
})

test('the detection evidence is shown for developers and whenever labeling is on', () => {
  assert.equal(showEvidence({ tuning: false, labeling: false }), false)
  assert.equal(showEvidence({ tuning: false, labeling: true }), true)
  assert.equal(showEvidence({ tuning: true, labeling: false }), true)
})
