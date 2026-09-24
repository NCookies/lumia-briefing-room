import assert from 'node:assert/strict'
import test from 'node:test'

import {
  describeProgress,
  describeResult,
  formatDuration,
  formatEstimate,
  isBackfillActive,
  progressPercent,
  type BackfillResult,
  type BackfillStatus,
} from '../src/backfill.ts'

const running = (over: Partial<BackfillStatus> = {}): BackfillStatus => ({
  state: 'running', phase: 'scan', fraction: 0.25, message: '', sessionIndex: 1, sessionTotal: 2,
  gamesDone: 0, gamesTotal: 0, clips: 0, error: null, result: null, ...over,
})

const result = (over: Partial<BackfillResult> = {}): BackfillResult => ({
  sessionsScanned: 2, gamesFound: 5, gamesProcessed: 3, gamesFailed: 0, clipsCreated: 20, cancelled: false,
  skipped: { known: 1, cutAtStart: 1, stillRunning: 0, alreadyDone: 0, gaveUp: 0 }, ...over,
})

test('estimate is rounded up to friendly whole units', () => {
  assert.equal(formatEstimate(0), '1분 미만')
  assert.equal(formatEstimate(20), '1분 미만')
  assert.equal(formatEstimate(90), '약 2분')
  assert.equal(formatEstimate(300), '약 5분')
  assert.equal(formatEstimate(3600), '약 1시간')
  assert.equal(formatEstimate(4800), '약 1시간 20분')
})

test('recording length reads as hours and minutes', () => {
  assert.equal(formatDuration(0), '0분')
  assert.equal(formatDuration(1800), '30분')
  assert.equal(formatDuration(9000), '2시간 30분')
  assert.equal(formatDuration(7200), '2시간')
})

test('active means running only', () => {
  assert.equal(isBackfillActive('running'), true)
  for (const s of ['idle', 'done', 'cancelled', 'error'] as const) assert.equal(isBackfillActive(s), false)
})

test('progress percent is clamped and rounded', () => {
  assert.equal(progressPercent(running({ fraction: 0.256 })), 26)
  assert.equal(progressPercent(running({ fraction: 2 })), 100)
  assert.equal(progressPercent(running({ fraction: -1 })), 0)
})

test('progress text tells the scan phase from the game phase', () => {
  assert.equal(describeProgress(running({ phase: 'scan', message: '77분 지점' })), '녹화를 살펴보는 중 · 세션 1/2 · 77분 지점')
  assert.equal(
    describeProgress(running({ phase: 'process', gamesDone: 2, gamesTotal: 5, clips: 14, message: '09-24 15:55 게임' })),
    '게임 분석 중 · 3/5 · 클립 14개 · 09-24 15:55 게임',
  )
})

test('progress text before anything is known is calm', () => {
  assert.equal(describeProgress(running({ phase: 'scan', sessionIndex: 0, sessionTotal: 0, message: '' })), '녹화를 살펴보는 중')
})

test('the finished summary names what was made and what was skipped and why', () => {
  const lines = describeResult(result())
  assert.equal(lines[0], '게임 3개에서 클립 20개를 만들었습니다.')
  assert.ok(lines.some((l) => l.includes('이미 클립이 있는 게임 1개')))
  assert.ok(lines.some((l) => l.includes('앞부분이 이미 지워진 게임 1개')))
})

test('nothing new is said plainly', () => {
  const lines = describeResult(
    result({ gamesProcessed: 0, clipsCreated: 0, skipped: { known: 3, cutAtStart: 0, stillRunning: 0, alreadyDone: 0, gaveUp: 0 } }),
  )
  assert.equal(lines[0], '새로 만들 게임이 없습니다.')
})

test('cancelled summary keeps what was already made and says it can resume', () => {
  const lines = describeResult(result({ cancelled: true, gamesProcessed: 2, clipsCreated: 11 }))
  assert.equal(lines[0], '취소했습니다. 그때까지 끝낸 게임 2개(클립 11개)는 그대로 남아 있습니다.')
  assert.ok(lines.some((l) => l.includes('다시 시작하면 이어서')))
})

test('failures and give-ups are mentioned', () => {
  const lines = describeResult(
    result({ gamesFailed: 1, skipped: { known: 0, cutAtStart: 0, stillRunning: 1, alreadyDone: 0, gaveUp: 2 } }),
  )
  assert.ok(lines.some((l) => l.includes('실패한 게임 1개')))
  assert.ok(lines.some((l) => l.includes('아직 진행 중인 게임 1개')))
  assert.ok(lines.some((l) => l.includes('여러 번 실패해 건너뛴 게임 2개')))
})
