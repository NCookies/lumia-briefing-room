import assert from 'node:assert/strict'
import test from 'node:test'

import { installProgressText, isInstallBusy, releaseSummary, showUpdateBanner, type UpdateStatus } from '../src/update.ts'

const release = { version: '0.2.0', notes: '', pageUrl: '' }
const base: UpdateStatus = {
  enabled: true,
  current: '0.1.3',
  lastChecked: null,
  available: release,
  install: { state: 'idle', downloaded: 0, total: 0, error: '' },
}

test('the banner shows only when auto check is on and a newer release is known', () => {
  assert.equal(showUpdateBanner(base), true)
  assert.equal(showUpdateBanner({ ...base, enabled: false }), false)
  assert.equal(showUpdateBanner({ ...base, available: null }), false)
})

test('install progress reads as percent while the size is known', () => {
  assert.equal(installProgressText({ state: 'downloading', downloaded: 50, total: 200, error: '' }), '받는 중 25%')
  assert.equal(installProgressText({ state: 'downloading', downloaded: 50, total: 0, error: '' }), '받는 중…')
  assert.equal(installProgressText({ state: 'verifying', downloaded: 200, total: 200, error: '' }), 'SHA-256 확인 중…')
  assert.match(installProgressText({ state: 'launched', downloaded: 0, total: 0, error: '' }), /곧 종료/)
  assert.equal(installProgressText({ state: 'failed', downloaded: 0, total: 0, error: '체크섬 불일치' }), '체크섬 불일치')
  assert.equal(installProgressText({ state: 'idle', downloaded: 0, total: 0, error: '' }), '')
})

test('buttons are locked while an install is running', () => {
  assert.equal(isInstallBusy('downloading'), true)
  assert.equal(isInstallBusy('verifying'), true)
  assert.equal(isInstallBusy('launching'), true)
  assert.equal(isInstallBusy('launched'), true)
  assert.equal(isInstallBusy('idle'), false)
  assert.equal(isInstallBusy('failed'), false)
})

test('release summary names the version', () => {
  assert.equal(releaseSummary(release), '새 버전 v0.2.0')
})
