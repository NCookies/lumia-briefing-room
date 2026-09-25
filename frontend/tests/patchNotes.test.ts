import assert from 'node:assert/strict'
import test from 'node:test'

import { formatReleaseDate, isCurrentRelease } from '../src/patchNotes.ts'

test('release dates read as Korean dates without leading zeros', () => {
  assert.equal(formatReleaseDate('2026-09-05'), '2026년 9월 5일')
  assert.equal(formatReleaseDate('2026-10-21'), '2026년 10월 21일')
})

test('a missing or malformed date shows nothing', () => {
  assert.equal(formatReleaseDate(''), '')
  assert.equal(formatReleaseDate('어제'), '')
})

test('only the running version is marked as current', () => {
  assert.equal(isCurrentRelease({ version: '0.1.3' }, '0.1.3'), true)
  assert.equal(isCurrentRelease({ version: '0.1.2' }, '0.1.3'), false)
  assert.equal(isCurrentRelease({ version: '0.1.3' }, ''), false)
})
