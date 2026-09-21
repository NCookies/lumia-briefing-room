import assert from 'node:assert/strict'
import test from 'node:test'

import { groupByGame } from '../src/grouping.ts'

const c = (id: string, matchStartUtc: string, sessionDir = 's1', pvpScore: number | null = null) => ({
  id,
  matchStartUtc,
  sessionDir,
  pvpScore,
})

const clips = [
  c('20260920_130000_02', '2026-09-20T13:00:00Z'),
  c('20260920_120000_01', '2026-09-20T12:00:00Z'),
  c('20260920_130000_01', '2026-09-20T13:00:00Z'),
  c('20260920_120000_02', '2026-09-20T12:00:00Z'),
]

test('groupByGame ascending orders games and clips oldest first', () => {
  const groups = groupByGame(clips, 'asc')
  assert.deepEqual(
    groups.map((g) => g.clips.map((x) => x.id)),
    [
      ['20260920_120000_01', '20260920_120000_02'],
      ['20260920_130000_01', '20260920_130000_02'],
    ],
  )
})

test('groupByGame descending orders games and clips newest first', () => {
  const groups = groupByGame(clips, 'desc')
  assert.deepEqual(
    groups.map((g) => g.clips.map((x) => x.id)),
    [
      ['20260920_130000_02', '20260920_130000_01'],
      ['20260920_120000_02', '20260920_120000_01'],
    ],
  )
})

test('groupByGame separates same start time in different sessions', () => {
  const groups = groupByGame([c('a', 't', 's1'), c('b', 't', 's2')], 'asc')
  assert.equal(groups.length, 2)
})

test('groupByGame pvp keeps games in time order and ranks clips by score', () => {
  const groups = groupByGame(
    [c('a', 't1', 's', 0.2), c('b', 't1', 's', 0.9), c('c', 't0', 's', null)],
    'pvp',
  )
  assert.deepEqual(
    groups.map((g) => g.clips.map((x) => x.id)),
    [['c'], ['b', 'a']],
  )
})

test('groupByGame numbers games from the oldest regardless of direction', () => {
  const groups = groupByGame(clips, 'desc')
  assert.deepEqual(groups.map((g) => g.number), [2, 1])
})
