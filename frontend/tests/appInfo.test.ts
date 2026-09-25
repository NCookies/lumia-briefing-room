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

test('header version text: release shows v-prefixed version, dev appends (dev)', async () => {
  const { versionLabel } = await import('../src/appInfo.ts')
  assert.equal(versionLabel({ version: '0.1.1', mode: 'release' }), 'v0.1.1')
  assert.equal(versionLabel({ version: '0.1.1', mode: 'dev' }), 'v0.1.1 (dev)')
})

test('header version text is empty when the version is unknown', async () => {
  const { versionLabel } = await import('../src/appInfo.ts')
  assert.equal(versionLabel({ version: '', mode: 'dev' }), '')
  assert.equal(versionLabel(DEFAULT_APP_INFO), '')
})

import { videoFormatHelpText } from '../src/appInfo.ts'

test('video format help lists supported and verified formats', () => {
  const text = videoFormatHelpText({ supported: ['.mkv', '.mp4', '.ts'], verified: ['.mp4'] })
  assert.match(text, /지원하는 영상 형식: \.mkv \.mp4 \.ts/)
  assert.match(text, /확인된 형식: \.mp4/)
  assert.match(text, /아직 확인되지 않았습니다/)
})

test('video format help drops the caveat once every format is verified', () => {
  const text = videoFormatHelpText({ supported: ['.mp4'], verified: ['.mp4'] })
  assert.doesNotMatch(text, /확인되지 않았습니다/)
})

test('video format help is empty until the formats are loaded', () => {
  assert.equal(videoFormatHelpText({ supported: [], verified: [] }), '')
})
