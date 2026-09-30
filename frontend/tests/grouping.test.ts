import assert from 'node:assert/strict'
import test from 'node:test'

import {
  formatAgo,
  formatKda,
  formatMatchResult,
  gameRecordId,
  groupByGame,
  resultImageRef,
  totalSize,
  withResultImage,
} from '../src/grouping.ts'

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

test('formatMatchResult drops the placement when it could not be read', () => {
  assert.equal(formatMatchResult(result({ matchType: 'normal', placement: null })), '일반')
  assert.equal(formatMatchResult(result({ matchType: 'unknown', placement: null })), null)
})

test('formatMatchResult shows an escape outcome but no character name(초상화로 대체, plan-ui.md §0)', () => {
  assert.equal(formatMatchResult(result({ placement: 3, outcome: '탈출 성공' })), '랭크 · 3위 · 탈출 성공')
})

test('formatMatchResult shows win/lose text for cobalt protocol instead of a placement, no character name', () => {
  assert.equal(formatMatchResult(result({ outcome: '승리', matchType: 'unknown' })), '승리')
  assert.equal(formatMatchResult(result({ outcome: '패배', matchType: 'unknown' })), '패배')
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

test('resultImageRef picks record, then clip, then falls back to the vod game summary', () => {
  // 실사용 사고(2026-09-27): 이 분기를 호출부마다 따로 적다가 clips[0] 이 없는
  // 경우(코발트처럼 교전은 못 뽑았어도 결과 화면은 읽은 VOD 게임)를 두 번 놓쳐서
  // 앱 전체가 죽었다 - 한 곳에 모아 테스트로 고정한다.
  assert.deepEqual(resultImageRef({ recordId: 'r1', clips: [{ id: 'c1' }], key: 'v1|2', number: 2 }), {
    kind: 'record',
    id: 'r1',
  })
  assert.deepEqual(resultImageRef({ clips: [{ id: 'c1' }], key: 'v1|2', number: 2 }), { kind: 'clip', id: 'c1' })
  assert.deepEqual(resultImageRef({ clips: [], key: 'v1|2', number: 2 }), {
    kind: 'vodGame',
    vodId: 'v1',
    index: 2,
  })
})

const record = (id: string, matchStartUtc: string, sessionDir = 's1') => ({
  id,
  sessionDir,
  matchStartUtc,
  matchResult: { matchType: 'rank' as const, matchLabel: '랭크', placement: 2, total: 8, outcome: null, nickname: null },
})

test('groupByGame adds clip-less rows for game records, ordered with the other games', () => {
  const groups = groupByGame(clips, 'asc', [record('r1', '2026-09-20T12:30:00Z')])
  assert.deepEqual(
    groups.map((g) => [g.matchStartUtc, g.clips.length, g.recordId ?? null]),
    [
      ['2026-09-20T12:00:00Z', 2, null],
      ['2026-09-20T12:30:00Z', 0, 'r1'],
      ['2026-09-20T13:00:00Z', 2, null],
    ],
  )
  assert.equal(groups[1].result?.placement, 2)
})

test('groupByGame ignores a record whose game still has clips', () => {
  const groups = groupByGame(clips, 'asc', [record('r1', '2026-09-20T12:00:00Z')])
  assert.equal(groups.length, 2)
  assert.equal(groups[0].recordId, undefined)
})

test('gameRecordId matches the server key', () => {
  assert.equal(gameRecordId('sess a', '2026-09-01T10:00:00Z'), 'sess_a__2026-09-01T10_00_00Z')
})

test('groupByGame carries the game mode from its clips', () => {
  const cobalt = { ...c('a', 't1', 's'), gameMode: 'cobalt' }
  const groups = groupByGame([cobalt], 'asc')
  assert.equal(groups[0].gameMode, 'cobalt')
})

test('groupByGame falls back to the game record mode when there are no clips', () => {
  const groups = groupByGame([], 'asc', [{ ...record('r1', '2026-09-20T12:00:00Z'), gameMode: 'cobalt' }])
  assert.equal(groups[0].gameMode, 'cobalt')
})
