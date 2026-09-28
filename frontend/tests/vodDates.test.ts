import assert from 'node:assert/strict'
import { test } from 'node:test'
import { formatDateChip, matchesDateFilter, uniqueVideoDates } from '../src/vodDates.ts'

test('formatDateChip prints month/day without leading zeros', () => {
  assert.equal(formatDateChip('2026-09-27'), '9/27')
  assert.equal(formatDateChip('2026-01-05'), '1/5')
  assert.equal(formatDateChip('2026-12-31'), '12/31')
})

test('uniqueVideoDates dedupes and sorts ascending, skipping nulls', () => {
  const vods = [{ videoDate: '2026-09-28' }, { videoDate: '2026-09-27' }, { videoDate: null }, { videoDate: '2026-09-27' }]
  assert.deepEqual(uniqueVideoDates(vods), ['2026-09-27', '2026-09-28'])
})

test('uniqueVideoDates returns empty array when nothing has a date', () => {
  assert.deepEqual(uniqueVideoDates([{ videoDate: null }]), [])
})

test('matchesDateFilter passes everything when no date is selected', () => {
  assert.equal(matchesDateFilter('2026-09-27', []), true)
  assert.equal(matchesDateFilter(null, []), true)
})

test('matchesDateFilter matches only the selected dates', () => {
  assert.equal(matchesDateFilter('2026-09-27', ['2026-09-27']), true)
  assert.equal(matchesDateFilter('2026-09-28', ['2026-09-27']), false)
})

test('matchesDateFilter rejects unknown dates when a date is selected', () => {
  assert.equal(matchesDateFilter(null, ['2026-09-27']), false)
})
