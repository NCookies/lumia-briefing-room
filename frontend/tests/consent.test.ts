import assert from 'node:assert/strict'
import test from 'node:test'

import {
  DEFAULT_CHOICES,
  LABEL_NOTE_MAX,
  LABEL_TEXT,
  clampLabelNote,
  consentPatch,
  isPending,
  showLabelingUi,
} from '../src/consent.ts'

test('every consent choice starts off', () => {
  assert.deepEqual(DEFAULT_CHOICES, { update: false, labels: false, logs: false })
})

test('patch contains only the pending items so earlier answers are kept', () => {
  const on = { update: true, labels: true, logs: true }
  assert.deepEqual(consentPatch(on, ['update']), { update: { check: true } })
  assert.deepEqual(consentPatch(on, ['setup', 'labels', 'logs']), {
    telemetry: { sendLabels: true, sendLogs: true },
  })
  assert.deepEqual(consentPatch(on, ['setup']), {})
})

test('patch writes explicit false when the user leaves an item off', () => {
  assert.deepEqual(consentPatch(DEFAULT_CHOICES, ['update', 'labels', 'logs']), {
    update: { check: false },
    telemetry: { sendLabels: false, sendLogs: false },
  })
})

test('isPending checks the pending item list', () => {
  assert.equal(isPending(['setup', 'update'], 'update'), true)
  assert.equal(isPending(['setup'], 'update'), false)
})

test('labeling UI shows in dev mode always, in release only when label sending is on', () => {
  assert.equal(showLabelingUi('dev', false), true)
  assert.equal(showLabelingUi('release', true), true)
  assert.equal(showLabelingUi('release', false), false)
})

test('label texts are combat / other', () => {
  assert.deepEqual(LABEL_TEXT, { pvp: '교전', pve: '그 외' })
})

test('label note is capped at 500 characters', () => {
  assert.equal(LABEL_NOTE_MAX, 500)
  assert.equal(clampLabelNote('가'.repeat(700)).length, 500)
  assert.equal(clampLabelNote('짧은 메모'), '짧은 메모')
})
