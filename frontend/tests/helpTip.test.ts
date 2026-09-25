import assert from 'node:assert/strict'
import test from 'node:test'

import { tooltipPlacement } from '../src/helpTip.ts'

test('opens below when there is room below', () => {
  assert.equal(tooltipPlacement({ top: 100, bottom: 120, viewportHeight: 800, needed: 300 }), 'below')
})

test('opens above when the button sits at the bottom of the screen', () => {
  assert.equal(tooltipPlacement({ top: 1050, bottom: 1070, viewportHeight: 1280, needed: 300 }), 'above')
})

test('opens on the roomier side when neither side fits', () => {
  assert.equal(tooltipPlacement({ top: 180, bottom: 200, viewportHeight: 400, needed: 300 }), 'below')
  assert.equal(tooltipPlacement({ top: 240, bottom: 260, viewportHeight: 400, needed: 300 }), 'above')
})
