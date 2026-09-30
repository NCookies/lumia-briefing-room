import assert from 'node:assert/strict'
import test from 'node:test'

import { storageUsage } from '../src/storageUsage.ts'

const GB = 1024 ** 3

test('no limit or auto clean off hides the bar', () => {
  assert.equal(storageUsage({ tabBytes: GB, totalBytes: GB, limitGb: null, autoCleanEnabled: true }), null)
  assert.equal(storageUsage({ tabBytes: GB, totalBytes: GB, limitGb: 40, autoCleanEnabled: false }), null)
  assert.equal(storageUsage({ tabBytes: GB, totalBytes: GB, limitGb: 0, autoCleanEnabled: true }), null)
})

test('label shows this tab share, the shared total and the limit', () => {
  const u = storageUsage({ tabBytes: 6.2 * GB, totalBytes: 10.8 * GB, limitGb: 40, autoCleanEnabled: true })!
  assert.equal(u.label, '이 탭 6.20 GB · 전체 10.80 GB / 40 GB')
  assert.equal(Math.round(u.percent), 27)
  assert.equal(u.level, 'ok')
})

test('level turns amber near the limit and red very close or over', () => {
  const at = (gb: number) => storageUsage({ tabBytes: gb * GB, totalBytes: gb * GB, limitGb: 40, autoCleanEnabled: true })!
  assert.equal(at(27).level, 'ok')
  assert.equal(at(30).level, 'warn')
  assert.equal(at(35.9).level, 'warn')
  assert.equal(at(36).level, 'full')
  assert.equal(at(45).level, 'full')
  assert.equal(at(45).percent, 100)
})

test('the this-tab part is left out when it equals the whole', () => {
  const u = storageUsage({ tabBytes: 5 * GB, totalBytes: 5 * GB, limitGb: 40, autoCleanEnabled: true, showTabShare: false })!
  assert.equal(u.label, '5.00 GB / 40 GB')
})
