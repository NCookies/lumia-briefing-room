import assert from 'node:assert/strict'
import test from 'node:test'

import { formatDayLabel, groupByDay, localDayKey } from '../src/gameDays.ts'

const at = (y: number, m: number, d: number, h: number, min = 0) => new Date(y, m - 1, d, h, min).toISOString()

test('localDayKey splits at local midnight', () => {
  assert.equal(localDayKey(at(2026, 9, 29, 23, 59)), '2026-09-29')
  assert.equal(localDayKey(at(2026, 9, 30, 0, 17)), '2026-09-30')
})

test('localDayKey returns null for missing or broken time', () => {
  assert.equal(localDayKey(''), null)
  assert.equal(localDayKey('not-a-date'), null)
})

test('groupByDay keeps the given game order and starts a new day when the date changes', () => {
  const games = [
    { key: 'g6', matchStartUtc: at(2026, 9, 30, 0, 48) },
    { key: 'g5', matchStartUtc: at(2026, 9, 30, 0, 25) },
    { key: 'g3', matchStartUtc: at(2026, 9, 29, 1, 37) },
    { key: 'g2', matchStartUtc: at(2026, 9, 29, 1, 0) },
  ]
  const days = groupByDay(games)
  assert.deepEqual(
    days.map((d) => [d.day, d.games.map((g) => g.key)]),
    [
      ['2026-09-30', ['g6', 'g5']],
      ['2026-09-29', ['g3', 'g2']],
    ],
  )
})

test('groupByDay works for ascending order too', () => {
  const games = [
    { key: 'a', matchStartUtc: at(2026, 9, 29, 1, 0) },
    { key: 'b', matchStartUtc: at(2026, 9, 30, 0, 25) },
  ]
  assert.deepEqual(
    groupByDay(games).map((d) => d.day),
    ['2026-09-29', '2026-09-30'],
  )
})

test('games without a known time go to one trailing group', () => {
  const games = [
    { key: 'x', matchStartUtc: '' },
    { key: 'a', matchStartUtc: at(2026, 9, 30, 0, 25) },
    { key: 'y', matchStartUtc: '' },
  ]
  const days = groupByDay(games)
  assert.deepEqual(
    days.map((d) => [d.day, d.games.map((g) => g.key)]),
    [
      ['2026-09-30', ['a']],
      [null, ['x', 'y']],
    ],
  )
})

test('formatDayLabel shows month, day, weekday and today/yesterday', () => {
  const now = new Date(2026, 8, 30, 9, 0)
  assert.equal(formatDayLabel('2026-09-30', now), '9월 30일 (수) · 오늘')
  assert.equal(formatDayLabel('2026-09-29', now), '9월 29일 (화) · 어제')
  assert.equal(formatDayLabel('2026-09-27', now), '9월 27일 (일)')
  assert.equal(formatDayLabel('2025-12-31', now), '2025년 12월 31일 (수)')
  assert.equal(formatDayLabel(null, now), '날짜 모름')
})
