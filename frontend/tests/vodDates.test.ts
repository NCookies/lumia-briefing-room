import assert from 'node:assert/strict'
import { test } from 'node:test'
import { formatDateChip, groupVodsByDate } from '../src/vodDates.ts'

test('formatDateChip prints month/day without leading zeros', () => {
  assert.equal(formatDateChip('2026-09-27'), '9/27')
  assert.equal(formatDateChip('2026-01-05'), '1/5')
  assert.equal(formatDateChip('2026-12-31'), '12/31')
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
