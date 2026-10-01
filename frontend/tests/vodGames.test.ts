import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildableGameCount,
  clipsOfVodGame,
  groupGamesByVod,
  vodGameHeading,
  vodGameTime,
  vodTotals,
} from '../src/vodGames.ts'

const vod = (id: string, name: string, extra: object = {}) => ({ id, name, videoDate: null, games: [], ...extra }) as never

const game = (vodId: string, index: number, extra: object = {}) =>
  ({
    key: `vod_${vodId}_g${String(index).padStart(2, '0')}`,
    source: 'vod',
    vodId,
    gameIndex: index,
    vodStartSec: 100 * index,
    vodEndSec: 100 * index + 1500,
    hasFullVideo: true,
    legacy: false,
    fullVideoDeletedAt: null,
    fullVideoSizeBytes: 1000,
    savedClipCount: 2,
    ...extra,
  }) as never

test('games are listed under their video in game-number order', () => {
  const groups = groupGamesByVod([vod('a', 'a.mp4')], [game('a', 2), game('a', 1), game('a', 10)])
  assert.deepEqual(groups[0].games.map((g) => g.gameIndex), [1, 2, 10])
})

test('a video without any game still gets a group (so it can be analysed) and groups are sorted by name', () => {
  const groups = groupGamesByVod([vod('b', 'b.mp4'), vod('a', '가.mp4')], [game('b', 1)])
  assert.deepEqual(groups.map((g) => [g.vodId, g.games.length]), [['a', 0], ['b', 1]])
})

test('games of a video that is gone from the list still show under its id', () => {
  const groups = groupGamesByVod([], [game('zzz', 1)])
  assert.deepEqual(groups.map((g) => [g.vodId, g.name, g.vod]), [['zzz', 'zzz', null]])
})

test('only old games without a full video (not auto-cleaned ones) can be built', () => {
  const games = [
    game('a', 1, { legacy: true, hasFullVideo: false }),
    game('a', 2, { legacy: true, hasFullVideo: false, fullVideoDeletedAt: '2026-09-30T00:00:00Z' }),
    game('a', 3),
    game('a', 4, { legacy: false, hasFullVideo: false }),
  ]
  assert.equal(buildableGameCount(games), 1)
})

test('totals of a video: games, saved clips and full video bytes', () => {
  const totals = vodTotals([game('a', 1), game('a', 2, { fullVideoSizeBytes: null, savedClipCount: 0 })])
  assert.deepEqual(totals, { games: 2, clips: 2, bytes: 1000 })
})

test('game time shows its number and where it sits in the video', () => {
  assert.deepEqual(vodGameTime(game('a', 3)), { main: '게임 3', sub: '0:05:00 ~ 0:30:00' })
  assert.deepEqual(vodGameTime({ gameIndex: 1, vodStartSec: null, vodEndSec: null } as never), { main: '게임 1', sub: '' })
})

test('the viewer heading names the streamer and game number', () => {
  assert.equal(vodGameHeading({ streamer: '하이용가리', vodGameIndex: 2 }), '하이용가리 · 게임 2')
  assert.equal(vodGameHeading({ streamer: null, vodGameIndex: 2 }), '게임 2')
})

test('saved clips of an old game come from its candidates, in time order', () => {
  const clips = clipsOfVodGame({
    candidates: [
      { id: 'c2', title: '두번째', start: 200, end: 240, user: { savedClipId: 'c2' } },
      { id: 'c1', title: '첫번째', start: 100, end: 130, user: { savedClipId: 'c1' } },
      { id: 'c3', title: '저장 안 함', start: 300, end: 330, user: {} },
    ],
    userCandidates: [],
  } as never)
  assert.deepEqual(clips.map((c) => [c.id, c.title, c.durationSec]), [['c1', '첫번째', 30], ['c2', '두번째', 40]])
})

test('games are reloaded whenever a running analysis stops running, even if the job poll missed "done"', async () => {
  const { analysisEnded } = await import('../src/vodGames.ts')
  assert.equal(analysisEnded('abc', null), true)
  assert.equal(analysisEnded('abc', 'def'), true)
  assert.equal(analysisEnded(null, 'abc'), false)
  assert.equal(analysisEnded('abc', 'abc'), false)
  assert.equal(analysisEnded(null, null), false)
})
