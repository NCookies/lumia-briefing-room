import assert from 'node:assert/strict'
import test from 'node:test'

import { DEFAULT_APP_INFO, showTuningUi } from '../src/appInfo.ts'

test('tuning screens show only in dev mode', () => {
  assert.equal(showTuningUi({ version: '0.1.0', mode: 'dev' }), true)
  assert.equal(showTuningUi({ version: '0.1.0', mode: 'release' }), false)
})

test('before app info loads, tuning screens stay hidden', () => {
  assert.equal(showTuningUi(DEFAULT_APP_INFO), false)
})
