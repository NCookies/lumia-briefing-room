import assert from 'node:assert/strict'
import { test } from 'node:test'
import { formatDateChip, groupVodsByDate, matchesDateFilter, uniqueVideoDates } from '../src/vodDates.ts'

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

const vg = (name: string, videoDate: string | null) => ({ name, vod: { videoDate } })

test('groupVodsByDate puts newest date first for desc and keeps name order inside a date', () => {
  const groups = [vg('가', '2026-09-27'), vg('나', '2026-09-28'), vg('다', '2026-09-27')]
  assert.deepEqual(
    groupVodsByDate(groups, 'desc').map((d) => [d.day, d.vods.map((v) => v.name)]),
    [
      ['2026-09-28', ['나']],
      ['2026-09-27', ['가', '다']],
    ],
  )
})

test('groupVodsByDate puts oldest date first for asc', () => {
  const groups = [vg('가', '2026-09-28'), vg('나', '2026-09-27')]
  assert.deepEqual(
    groupVodsByDate(groups, 'asc').map((d) => d.day),
    ['2026-09-27', '2026-09-28'],
  )
})

test('groupVodsByDate puts videos without a date (or without an index entry) last', () => {
  const groups = [vg('가', null), { name: '나', vod: null }, vg('다', '2026-09-27')]
  assert.deepEqual(
    groupVodsByDate(groups, 'desc').map((d) => [d.day, d.vods.map((v) => v.name)]),
    [
      ['2026-09-27', ['다']],
      [null, ['가', '나']],
    ],
  )
})
