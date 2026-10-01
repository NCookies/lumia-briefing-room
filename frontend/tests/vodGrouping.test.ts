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
    sourceDeleted: false,
    sizeBytes: 1000,
    durationSec: 3600,
    width: 1920,
    height: 1080,
    status: 'done',
    analyzedSec: 3600,
    error: null,
    errorKind: null,
    streamer: null,
    videoDate: null,
    games: [],
    clipCount: 0,
    clipBytes: 0,
    probing: false,
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

test('groupByVod carries the game mode from its clips', () => {
  const groups = groupByVod([clip('c1', 'v1', 1, { gameMode: 'cobalt' })], [vod()], 'asc', true)

  assert.equal(groups[0].games[0].gameMode, 'cobalt')
})

test('desc reverses games, clips stay ascending', () => {
  const clips = [clip('a', 'v1', 1, { pvpScore: 0.2 }), clip('b', 'v1', 2, { pvpScore: 0.9 }), clip('c', 'v1', 3, { pvpScore: 0.5 })]

  assert.deepEqual(groupByVod(clips, [vod()], 'desc', true)[0].games.map((g) => g.number), [3, 2, 1])
})

test('vods are ordered by name and clips of unknown vods still appear', () => {
  const groups = groupByVod(
    [clip('x', 'v9', 1)],
    [vod({ id: 'v2', name: 'b.mp4', status: 'new' }), vod({ id: 'v1', name: 'A.mp4', status: 'new' })],
    'asc',
    true,
  )

  assert.deepEqual(groups.map((g) => g.vodId), ['v1', 'v2', 'v9'])
  assert.equal(groups[2].vod, null)
  assert.equal(groups[2].name, 'v9')
})

test('vods without clips are kept only when includeEmpty is set', () => {
  const vods = [vod({ id: 'v1', clipCount: 1 }), vod({ id: 'v2', name: 'b.mp4', status: 'new' })]
  const clips = [clip('c', 'v1', 1)]

  assert.deepEqual(groupByVod(clips, vods, 'asc', true).map((g) => g.vodId), ['v1', 'v2'])
  assert.deepEqual(groupByVod(clips, vods, 'asc', false).map((g) => g.vodId), ['v1'])
})

test('an analyzed vod with zero clips still stays in the list (no auto-hiding)', () => {
  // 실사용 사고(2026-09-27): "분석 완료 + 클립 0개"를 숨기는 조건이 "게임을 못
  // 찾음"과 "게임은 찾았는데 클립을 지움"을 구분 못 해, 못 찾은 영상까지 사라져
  // 다시 분석할 방법이 없었다. 조건을 더 세분화하는 대신 아예 숨기지 않기로
  // 했다 - 보기 싫으면 사용자가 직접 지운다.
  const vods = [
    vod({ id: 'v1', clipCount: 0, status: 'done', games: [] }),
    vod({ id: 'v2', name: 'b.mp4', clipCount: 0, status: 'new' }),
    vod({ id: 'v3', name: 'c.mp4', clipCount: 0, status: 'interrupted' }),
    vod({ id: 'v4', name: 'd.mp4', clipCount: 3, status: 'done' }),
  ]

  assert.deepEqual(groupByVod([], vods, 'asc', true).map((g) => g.vodId), ['v1', 'v2', 'v3', 'v4'])
})

test('games with no clips still show up as rows using the vod summary (plan.md §10-6)', () => {
  // 실사용 사고: 코발트 다시보기가 교전은 못 뽑았어도(오버레이 문제, §10-3) 결과
  // 화면(승패·스탯·팀원)은 6판 다 읽었는데, 클립 기준으로만 게임 행을 만들다 보니
  // "게임 6개"라고 세면서 화면엔 아무 행도 안 보였다.
  const win = { matchType: 'unknown', matchLabel: '', placement: 1, total: 2, outcome: '승리', nickname: '우쮸' }
  const vods = [
    vod({
      id: 'v1',
      status: 'done',
      games: [
        { index: 1, startSec: 0, endSec: 500, gameMode: 'cobalt', result: win, clipIds: [] },
        { index: 2, startSec: 600, endSec: 1000, gameMode: 'cobalt', result: null, clipIds: [] },
      ],
    }),
  ]

  const groups = groupByVod([], vods, 'asc', true)

  assert.equal(groups[0].games.length, 2)
  assert.deepEqual(groups[0].games[0].clips, [])
  assert.equal(groups[0].games[0].result, win)
  assert.equal(groups[0].games[0].gameMode, 'cobalt')
  assert.deepEqual([groups[0].games[0].startSec, groups[0].games[0].endSec], [0, 500])
})

test('a game with both a live clip and a zero-clip summary entry is not duplicated', () => {
  const vods = [
    vod({ id: 'v1', status: 'done', games: [{ index: 1, startSec: 0, endSec: 500, result: null, clipIds: ['c1'] }] }),
  ]

  const groups = groupByVod([clip('c1', 'v1', 1)], vods, 'asc', true)

  assert.equal(groups[0].games.length, 1)
  assert.equal(groups[0].games[0].clips.length, 1)
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
  assert.equal(vodStatusLabel('queued'), '대기 중')
  assert.equal(vodStatusLabel('analyzing'), '분석 중')
  assert.equal(vodStatusLabel('interrupted'), '분석 중단됨')
  assert.equal(vodStatusLabel('cancelled'), '분석 취소됨')
  assert.equal(vodStatusLabel('error'), '분석 실패')
  assert.equal(vodStatusLabel('done'), '분석 완료')
  assert.equal(analysisPercent(vod({ analyzedSec: 1800, durationSec: 3600 })), 50)
  assert.equal(analysisPercent(vod({ analyzedSec: null })), 0)
  assert.equal(analysisPercent(vod({ analyzedSec: 9999, durationSec: 3600 })), 100)
})

import { probeProgress } from '../src/vodGrouping.ts'

test('probe progress counts the videos whose length is still being read', () => {
  const vods = [vod({ id: 'a', probing: true }), vod({ id: 'b', probing: false }), vod({ id: 'c', probing: true }), vod({ id: 'd' })]
  assert.deepEqual(probeProgress(vods), { total: 4, pending: 2, done: 2, percent: 50, active: true })
})

test('probe progress is inactive when nothing is being read', () => {
  assert.deepEqual(probeProgress([vod({ id: 'a' })]), { total: 1, pending: 0, done: 1, percent: 100, active: false })
  assert.deepEqual(probeProgress([]), { total: 0, pending: 0, done: 0, percent: 100, active: false })
})

import { analysisBlockedReason } from '../src/vodGrouping.ts'

test('a disabled analysis button always says why', () => {
  assert.equal(analysisBlockedReason(vod()), '')
  assert.match(analysisBlockedReason(vod({ exists: false })), /찾을 수 없/)
  assert.equal(analysisBlockedReason(null), '')
})

test('a source deleted by the auto-delete setting gets its own reason, not "file missing"', () => {
  const reason = analysisBlockedReason(vod({ exists: false, sourceDeleted: true }))
  assert.match(reason, /자동 삭제/)
  assert.doesNotMatch(reason, /찾을 수 없/)
})

test('원본이 없어도 저장한 풀영상이 있으면 다시 분석 버튼이 막히지 않는다', () => {
  assert.equal(analysisBlockedReason(vod({ exists: false, canReanalyzeFromFullVideos: true })), '')
})
