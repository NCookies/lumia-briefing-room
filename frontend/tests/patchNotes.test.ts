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

import { parseReleaseNotes } from '../src/patchNotes.ts'

test('release notes markdown becomes titled sections of bullet items', () => {
  const md = '### 새로 생겼어요\n- **첫째** 항목\n- 둘째 항목\n\n### 좋아졌어요\n* 셋째\n'
  assert.deepEqual(parseReleaseNotes(md), [
    { title: '새로 생겼어요', items: ['**첫째** 항목', '둘째 항목'] },
    { title: '좋아졌어요', items: ['셋째'] },
  ])
})

test('the checksum footer after the divider is not part of the notes', () => {
  const md = '### 고쳤어요\n- 하나\n\n---\n\n**setup.exe** 의 SHA-256: `abc`\n'
  assert.deepEqual(parseReleaseNotes(md), [{ title: '고쳤어요', items: ['하나'] }])
})

test('bullets before any heading go into an untitled section, empty notes give nothing', () => {
  assert.deepEqual(parseReleaseNotes('- 제목 없는 항목'), [{ title: '', items: ['제목 없는 항목'] }])
  assert.deepEqual(parseReleaseNotes(''), [])
})
