import assert from 'node:assert/strict'
import test from 'node:test'

import { formatAgo, formatKda, formatMatchResult, formatTeammates, groupByGame, totalSize, withResultImage } from '../src/grouping.ts'

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

test('groupByGame descending orders games newest first but keeps clips oldest first', () => {
  const groups = groupByGame(clips, 'desc')
  assert.deepEqual(
    groups.map((g) => g.clips.map((x) => x.id)),
    [
      ['20260920_130000_01', '20260920_130000_02'],
      ['20260920_120000_01', '20260920_120000_02'],
    ],
  )
})

test('groupByGame separates same start time in different sessions', () => {
  const groups = groupByGame([c('a', 't', 's1'), c('b', 't', 's2')], 'asc')
  assert.equal(groups.length, 2)
})

test('groupByGame pvp orders games by their best score and keeps clips oldest first', () => {
  const groups = groupByGame(
    [
      c('a2', 't1', 's', 0.9),
      c('a1', 't1', 's', 0.2),
      c('b1', 't2', 's', 0.5),
      c('c1', 't0', 's', null),
    ],
    'pvp',
  )
  assert.deepEqual(
    groups.map((g) => g.clips.map((x) => x.id)),
    [['a1', 'a2'], ['b1'], ['c1']],
  )
})

test('groupByGame pvp breaks score ties by oldest game first', () => {
  const groups = groupByGame([c('b', 't2', 's', 0.5), c('a', 't1', 's', 0.5)], 'pvp')
  assert.deepEqual(groups.map((g) => g.clips[0].id), ['a', 'b'])
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

const result = (over = {}) => ({
  matchType: 'rank' as const,
  matchLabel: '랭크',
  placement: 4,
  total: 7,
  outcome: '실험 종료',
  nickname: null,
  ...over,
})

test('formatMatchResult writes type and placement without team count or routine outcome', () => {
  assert.equal(formatMatchResult(result()), '랭크 · 4위')
  assert.equal(formatMatchResult(result({ matchType: 'normal', placement: 1, outcome: '최종 생존' })), '일반 · 1위')
  assert.equal(formatMatchResult(null), null)
})

test('formatMatchResult omits the game type when it could not be read', () => {
  assert.equal(formatMatchResult(result({ matchType: 'unknown', placement: 2 })), '2위')
})

test('formatMatchResult leads with the character name and shows an escape outcome', () => {
  assert.equal(formatMatchResult(result({ placement: 1, character: '마커스' })), '마커스 · 랭크 · 1위')
  assert.equal(formatMatchResult(result({ placement: 3, outcome: '탈출 성공' })), '랭크 · 3위 · 탈출 성공')
})

test('formatKda joins TK/K/A and needs all three', () => {
  assert.equal(formatKda(result({ tk: 13, kills: 3, assists: 6 })), '13 / 3 / 6')
  assert.equal(formatKda(result({ tk: 2, kills: 0, assists: 0 })), '2 / 0 / 0')
  assert.equal(formatKda(result({ tk: 13, kills: null, assists: 6 })), null)
  assert.equal(formatKda(null), null)
})

test('formatAgo picks minutes, hours or days', () => {
  const now = new Date('2026-09-21T12:00:00Z')
  assert.equal(formatAgo('2026-09-21T11:30:00Z', now), '30분 전')
  assert.equal(formatAgo('2026-09-21T09:00:00Z', now), '3시간 전')
  assert.equal(formatAgo('2026-09-19T12:00:00Z', now), '2일 전')
  assert.equal(formatAgo('2026-09-21T11:59:40Z', now), '방금 전')
  assert.equal(formatAgo('not a date', now), '')
})

test('totalSize adds clip sizes and treats a missing size as zero', () => {
  assert.equal(totalSize([{ sizeBytes: 100 }, { sizeBytes: 250 }, {}]), 350)
  assert.equal(totalSize([]), 0)
})

test('withResultImage keeps only games that have a saved result screenshot, in the given order', () => {
  const shot = { ...result(), imagePath: 'x.jpg' }
  const groups = groupByGame(
    [
      { ...c('a', 't1', 's'), matchResult: shot },
      { ...c('b', 't2', 's'), matchResult: result() },
      { ...c('c', 't3', 's'), matchResult: shot },
    ],
    'desc',
  )

  assert.deepEqual(withResultImage(groups).map((g) => g.clips[0].id), ['c', 'a'])
})

test('formatTeammates lists teammate characters and falls back to the nickname when unknown', () => {
  const teammates = [
    { nickname: '팀원가', character: '루치아' },
    { nickname: 'TeamMateB', character: null },
  ]
  assert.equal(formatTeammates(result({ teammates })), '루치아, TeamMateB')
  assert.equal(formatTeammates(result({ teammates: [] })), null)
  assert.equal(formatTeammates(result()), null)
  assert.equal(formatTeammates(null), null)
})
