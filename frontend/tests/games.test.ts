import assert from 'node:assert/strict'
import test from 'node:test'

import {
  dragRange,
  candidateTitle,
  effectiveRange,
  formatClock,
  gameHeadline,
  matchTypeLabel,
  neighborCandidate,
  positionPct,
  timeFromPointer,
  visibleCandidates,
  type Candidate,
} from '../src/games.ts'

const c = (id: string, start: number, end: number, extra: Partial<Candidate> = {}): Candidate => ({
  id,
  start,
  end,
  title: id,
  tags: [],
  certain: false,
  user: {},
  ...extra,
})

test('the users adjusted range wins over the detected one and stays inside the video', () => {
  assert.deepEqual(effectiveRange(c('a', 10, 40), 600), [10, 40])
  assert.deepEqual(effectiveRange(c('a', 10, 40, { user: { start: 5, end: 50 } }), 600), [5, 50])
  assert.deepEqual(effectiveRange(c('a', -3, 700), 600), [0, 600])
})

test('dismissed candidates are hidden unless asked for, and the rest are sorted by start', () => {
  const game = {
    candidates: [c('b', 100, 130), c('a', 10, 40, { user: { dismissed: true } })],
    userCandidates: [c('u', 50, 70)],
  }
  assert.deepEqual(visibleCandidates(game).map((x) => x.id), ['u', 'b'])
  assert.deepEqual(visibleCandidates(game, true).map((x) => x.id), ['a', 'u', 'b'])
})

test('position and pointer conversions clamp to the bar', () => {
  assert.equal(positionPct(150, 600), 25)
  assert.equal(positionPct(700, 600), 100)
  assert.equal(positionPct(5, 0), 0)
  assert.equal(timeFromPointer(150, 100, 200, 600), 150)
  assert.equal(timeFromPointer(50, 100, 200, 600), 0)
  assert.equal(timeFromPointer(999, 100, 200, 600), 600)
})

test('previous and next candidate jump by start time and can be limited to certain ones', () => {
  const list = [c('a', 10, 40, { certain: true }), c('b', 100, 130), c('c', 200, 230, { certain: true })]
  assert.equal(neighborCandidate(list, 0, 'next', 600)?.id, 'a')
  assert.equal(neighborCandidate(list, 10, 'next', 600)?.id, 'b')
  assert.equal(neighborCandidate(list, 10, 'next', 600, true)?.id, 'c')
  assert.equal(neighborCandidate(list, 100, 'prev', 600)?.id, 'a')
  assert.equal(neighborCandidate(list, 250, 'next', 600), null)
  assert.equal(neighborCandidate(list, 5, 'prev', 600), null)
})

test('dismissed candidates are skipped when jumping', () => {
  const list = [c('a', 10, 40), c('b', 100, 130, { user: { dismissed: true } }), c('c', 200, 230)]
  assert.equal(neighborCandidate(list, 10, 'next', 600)?.id, 'c')
})

test('dragging a handle keeps the range inside the video and at least one second long', () => {
  assert.deepEqual(dragRange('start', [10, 40], -20, 600), [0, 40])
  assert.deepEqual(dragRange('start', [10, 40], 100, 600), [39, 40])
  assert.deepEqual(dragRange('end', [10, 40], 700, 600), [10, 600])
  assert.deepEqual(dragRange('end', [10, 40], -100, 600), [10, 11])
  assert.deepEqual(dragRange('move', [10, 40], 5, 600), [15, 45])
  assert.deepEqual(dragRange('move', [10, 40], -50, 600), [0, 30])
  assert.deepEqual(dragRange('move', [10, 40], 9999, 600), [570, 600])
})

test('clock text uses m:ss under an hour and h:mm:ss above', () => {
  assert.equal(formatClock(75), '1:15')
  assert.equal(formatClock(3725), '1:02:05')
  assert.equal(formatClock(-4), '0:00')
})

test('the headline shows the placement as #N, win/loss for cobalt, or says the result is unknown', () => {
  assert.equal(gameHeadline({ placement: 1, total: 7 }), '#1')
  assert.equal(gameHeadline({ placement: 7 }), '#7')
  assert.equal(gameHeadline({ placement: 2, outcome: '승리' }), '승리')
  assert.equal(gameHeadline({ outcome: '패배' }), '패배')
  assert.equal(gameHeadline({ placement: 3, outcome: '탈출' }), '#3')
  assert.equal(gameHeadline({ placement: null, matchType: 'normal' }), '순위 미확인')
  assert.equal(gameHeadline(null), '결과 미확인')
})

test('the match type shows as 랭크 or 일반 and stays hidden when unknown', () => {
  assert.equal(matchTypeLabel({ matchType: 'rank' }), '랭크')
  assert.equal(matchTypeLabel({ matchType: 'normal' }), '일반')
  assert.equal(matchTypeLabel({ matchType: 'unknown', matchLabel: '' }), '')
  assert.equal(matchTypeLabel({ placement: 1 }), '')
  assert.equal(matchTypeLabel(null), '')
})

test('the users title wins over the detected one', () => {
  assert.equal(candidateTitle(c('a', 1, 5, { title: '1일차 낮 교전' })), '1일차 낮 교전')
  assert.equal(candidateTitle(c('a', 1, 5, { title: '1일차 낮 교전', user: { title: '내 이름' } })), '내 이름')
})
