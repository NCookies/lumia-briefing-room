import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  analysisPercent,
  formatDuration,
  formatGameRange,
  groupByVod,
  vodStatusLabel,
  type Vod,
} from '../src/vodGrouping.ts'

function vod(over: Partial<Vod> = {}): Vod {
  return {
    id: 'v1',
    path: 'H:/vod/a.mp4',
    name: 'a.mp4',
    exists: true,
    sizeBytes: 1000,
    durationSec: 3600,
    width: 1920,
    height: 1080,
    status: 'done',
    analyzedSec: 3600,
    error: null,
    streamer: null,
    games: [],
    clipCount: 0,
    clipBytes: 0,
    trashedCount: 0,
    ...over,
  }
}

function clip(id: string, vodId: string, game: number, over: Record<string, unknown> = {}) {
  return {
    id,
    vodId,
    vodGameIndex: game,
    gameStartOffsetSec: game * 1000,
    gameEndOffsetSec: game * 1000 + 900,
    pvpScore: 0.5,
    matchResult: null,
    ...over,
  }
}

test('groupByVod puts clips under their vod and game, games ascending by default', () => {
  const groups = groupByVod(
    [clip('c3', 'v1', 2), clip('c1', 'v1', 1), clip('c2', 'v1', 1)],
    [vod()],
    'asc',
    true,
  )

  assert.equal(groups.length, 1)
  assert.deepEqual(groups[0].games.map((g) => g.number), [1, 2])
  assert.deepEqual(groups[0].games[0].clips.map((c) => c.id), ['c1', 'c2'])
  assert.equal(groups[0].games[0].startSec, 1000)
  assert.equal(groups[0].games[0].endSec, 1900)
})

test('desc reverses games and pvp sorts by the best score, clips stay ascending', () => {
  const clips = [clip('a', 'v1', 1, { pvpScore: 0.2 }), clip('b', 'v1', 2, { pvpScore: 0.9 }), clip('c', 'v1', 3, { pvpScore: 0.5 })]

  assert.deepEqual(groupByVod(clips, [vod()], 'desc', true)[0].games.map((g) => g.number), [3, 2, 1])
  assert.deepEqual(groupByVod(clips, [vod()], 'pvp', true)[0].games.map((g) => g.number), [2, 3, 1])
})

test('vods are ordered by name and clips of unknown vods still appear', () => {
  const groups = groupByVod(
    [clip('x', 'v9', 1)],
    [vod({ id: 'v2', name: 'b.mp4' }), vod({ id: 'v1', name: 'A.mp4' })],
    'asc',
    true,
  )

  assert.deepEqual(groups.map((g) => g.vodId), ['v1', 'v2', 'v9'])
  assert.equal(groups[2].vod, null)
  assert.equal(groups[2].name, 'v9')
})

test('vods without clips are kept only when includeEmpty is set', () => {
  const vods = [vod({ id: 'v1' }), vod({ id: 'v2', name: 'b.mp4' })]
  const clips = [clip('c', 'v1', 1)]

  assert.deepEqual(groupByVod(clips, vods, 'asc', true).map((g) => g.vodId), ['v1', 'v2'])
  assert.deepEqual(groupByVod(clips, vods, 'asc', false).map((g) => g.vodId), ['v1'])
})

test('the game result comes from the first clip that has one', () => {
  const result = { matchType: 'rank', matchLabel: '랭크', placement: 2, total: 8, outcome: null, nickname: null }
  const groups = groupByVod(
    [clip('a', 'v1', 1), clip('b', 'v1', 1, { matchResult: result })],
    [vod()],
    'asc',
    true,
  )

  assert.equal(groups[0].games[0].result?.placement, 2)
})

test('formatDuration prints h:mm:ss and m:ss', () => {
  assert.equal(formatDuration(13667), '3:47:47')
  assert.equal(formatDuration(75), '1:15')
  assert.equal(formatDuration(0), '0:00')
  assert.equal(formatDuration(null), '')
})

test('formatGameRange prints the position inside the video', () => {
  assert.equal(formatGameRange(2302, 3126), '0:38:22 ~ 0:52:06')
})

test('vodStatusLabel and analysisPercent', () => {
  assert.equal(vodStatusLabel('new'), '분석 안 함')
  assert.equal(vodStatusLabel('analyzing'), '분석 중')
  assert.equal(vodStatusLabel('interrupted'), '분석 중단됨')
  assert.equal(vodStatusLabel('cancelled'), '분석 취소됨')
  assert.equal(vodStatusLabel('error'), '분석 실패')
  assert.equal(vodStatusLabel('done'), '분석 완료')
  assert.equal(analysisPercent(vod({ analyzedSec: 1800, durationSec: 3600 })), 50)
  assert.equal(analysisPercent(vod({ analyzedSec: null })), 0)
  assert.equal(analysisPercent(vod({ analyzedSec: 9999, durationSec: 3600 })), 100)
})
