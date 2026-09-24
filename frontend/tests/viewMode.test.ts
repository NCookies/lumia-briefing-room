import assert from 'node:assert/strict'
import test from 'node:test'

import { loadViewMode, parseViewMode } from '../src/viewMode.ts'

test('parseViewMode accepts only timeline and defaults to cards', () => {
  assert.equal(parseViewMode('timeline'), 'timeline')
  assert.equal(parseViewMode('cards'), 'cards')
  assert.equal(parseViewMode(null), 'cards')
  assert.equal(parseViewMode('junk'), 'cards')
})

test('loadViewMode falls back to cards when localStorage is unavailable', () => {
  assert.equal(loadViewMode('steam'), 'cards')
})
