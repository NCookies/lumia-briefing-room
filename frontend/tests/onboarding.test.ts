import assert from 'node:assert/strict'
import test from 'node:test'

import { RESOLUTION_TONE, recordingState, type RecordingReport } from '../src/onboarding.ts'

const base: RecordingReport = { root: 'H:/video', source: 'auto', exists: true, session: null, resolution: null }

test('recording state distinguishes missing root, missing folder, no session, ok', () => {
  assert.equal(recordingState({ ...base, root: null, source: null, exists: false }), 'no-root')
  assert.equal(recordingState({ ...base, exists: false }), 'missing-folder')
  assert.equal(recordingState(base), 'no-session')
  assert.equal(
    recordingState({ ...base, session: { name: 'bg_1', width: 2560, height: 1440, codec: null } }),
    'ok',
  )
})

test('unsupported aspect ratio is a warning, measured is ok', () => {
  assert.equal(RESOLUTION_TONE.measured, 'ok')
  assert.equal(RESOLUTION_TONE.scaled, 'info')
  assert.equal(RESOLUTION_TONE.unsupported_ratio, 'warn')
})

import { canOfferFirstBackfill, type FirstRunInfo } from '../src/onboarding.ts'

const session = { name: 'bg_1', width: 2560, height: 1440, codec: null }
const info: FirstRunInfo = {
  needed: true,
  pendingItems: ['setup', 'update'],
  answeredVersion: 0,
  currentVersion: 3,
  recording: { ...base, session },
  clipsDir: 'C:/clips',
  ffmpegFound: true,
}

test('the past-recording analysis is offered on a first run when the recording folder and ffmpeg are there', () => {
  assert.equal(canOfferFirstBackfill(info), true)
})

test('the past-recording analysis is not offered without a recognised recording, without ffmpeg, or on a consent-only prompt', () => {
  assert.equal(canOfferFirstBackfill({ ...info, recording: { ...base, session: null } }), false)
  assert.equal(canOfferFirstBackfill({ ...info, recording: { ...base, root: null, exists: false, session } }), false)
  assert.equal(canOfferFirstBackfill({ ...info, ffmpegFound: false }), false)
  assert.equal(canOfferFirstBackfill({ ...info, pendingItems: ['update', 'labels'] }), false)
})
