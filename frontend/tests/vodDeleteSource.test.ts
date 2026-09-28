import assert from 'node:assert/strict'
import test from 'node:test'

import { needsAlwaysPermanentWarning, resolvedDeleteSource } from '../src/vodDeleteSource.ts'

test('always/never resolve without asking', () => {
  assert.equal(resolvedDeleteSource('always'), true)
  assert.equal(resolvedDeleteSource('never'), false)
})

test('ask needs a prompt, signalled by null', () => {
  assert.equal(resolvedDeleteSource('ask'), null)
})

test('always + permanent needs an extra warning before saving', () => {
  assert.equal(needsAlwaysPermanentWarning('always', 'permanent'), true)
  assert.equal(needsAlwaysPermanentWarning('always', 'trash'), false)
  assert.equal(needsAlwaysPermanentWarning('ask', 'permanent'), false)
  assert.equal(needsAlwaysPermanentWarning('never', 'permanent'), false)
})
