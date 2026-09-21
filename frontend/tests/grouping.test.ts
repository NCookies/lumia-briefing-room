import assert from 'node:assert/strict'
import test from 'node:test'

import { formatMatchResult, groupByGame } from '../src/grouping.ts'

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

test('groupByGame exposes the first known match result of the game', () => {
  const result = { matchType: 'rank', matchLabel: '랭크', placement: 4, total: 7, outcome: '실험 종료', nickname: 'a' }
  const groups = groupByGame(
    [
      { ...c('a', 't', 's'), matchResult: null },
      { ...c('b', 't', 's'), matchResult: result },
    ],
    'asc',
  )
  assert.deepEqual(groups[0].result, result)
})

test('formatMatchResult writes type, placement and outcome', () => {
  assert.equal(
    formatMatchResult({ matchType: 'rank', matchLabel: '랭크', placement: 4, total: 7, outcome: '실험 종료', nickname: null }),
    '랭크 · 4위 / 7팀 · 실험 종료',
  )
  assert.equal(
    formatMatchResult({ matchType: 'normal', matchLabel: '', placement: 1, total: 8, outcome: null, nickname: null }),
    '일반 · 1위 / 8팀',
  )
  assert.equal(formatMatchResult(null), null)
})

test('formatMatchResult omits the game type when it could not be read', () => {
  assert.equal(
    formatMatchResult({ matchType: 'unknown', matchLabel: '', placement: 2, total: 8, outcome: '실험 종료', nickname: null }),
    '2위 / 8팀 · 실험 종료',
  )
})

test('formatMatchResult leads with the character name when known', () => {
  assert.equal(
    formatMatchResult({
      matchType: 'rank', matchLabel: '랭크', placement: 1, total: 8, outcome: '최종 생존', nickname: null, character: '마커스',
    }),
    '마커스 · 랭크 · 1위 / 8팀 · 최종 생존',
  )
})
