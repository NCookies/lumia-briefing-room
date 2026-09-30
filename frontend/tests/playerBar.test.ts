import assert from 'node:assert/strict'
import test from 'node:test'

import type { Candidate } from '../src/games.ts'
import {
  applyMark,
  barPct,
  candidateAtTime,
  candidateAtBar,
  newRangeAround,
  panView,
  rangeModified,
  zoomBy,
  timeFromBar,
  tickStep,
  zoomView,
} from '../src/playerBar.ts'

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

test('bar position and time convert both ways for the whole video', () => {
  const view: [number, number] = [0, 600]
  assert.equal(barPct(150, view), 25)
  assert.equal(timeFromBar(300, 100, 400, view), 300)
  assert.equal(timeFromBar(50, 100, 400, view), 0)
  assert.equal(timeFromBar(900, 100, 400, view), 600)
})

test('a zoomed view maps the full bar width onto the window', () => {
  const view: [number, number] = [100, 200]
  assert.equal(barPct(150, view), 50)
  assert.equal(barPct(50, view), 0)
  assert.equal(barPct(300, view), 100)
  assert.equal(timeFromBar(250, 0, 500, view), 150)
})

test('a degenerate bar or view never yields NaN', () => {
  assert.equal(barPct(5, [10, 10]), 0)
  assert.equal(timeFromBar(5, 0, 0, [0, 100]), 0)
})

test('zoom shows thirty seconds around the candidate and stays inside the video', () => {
  assert.deepEqual(zoomView([100, 130], 600), [70, 160])
  assert.deepEqual(zoomView([10, 20], 600), [0, 50])
  assert.deepEqual(zoomView([580, 595], 600), [550, 600])
})

test('the candidate under the pressed spot is found even inside a yellow range', () => {
  const list = [c('a', 10, 40), c('b', 100, 130)]
  assert.equal(candidateAtTime(list, 25, 600)?.id, 'a')
  assert.equal(candidateAtTime(list, 70, 600), null)
  assert.equal(candidateAtTime(list, 130, 600)?.id, 'b')
})

test('overlapping ranges resolve to the narrower one and skip dismissed candidates', () => {
  const list = [c('wide', 0, 100), c('narrow', 40, 50), c('gone', 42, 44, { user: { dismissed: true } })]
  assert.equal(candidateAtTime(list, 45, 600)?.id, 'narrow')
  assert.equal(candidateAtTime(list, 10, 600)?.id, 'wide')
})

test('the users adjusted range decides which candidate holds the position', () => {
  const list = [c('a', 10, 40, { user: { start: 50, end: 80 } })]
  assert.equal(candidateAtTime(list, 25, 600), null)
  assert.equal(candidateAtTime(list, 60, 600)?.id, 'a')
})

test('candidateAtBar uses the zoomed view when converting the pointer', () => {
  const list = [c('a', 150, 160)]
  assert.equal(candidateAtBar(list, 250, 0, 500, [100, 200], 600)?.id, 'a')
  assert.equal(candidateAtBar(list, 250, 0, 500, [0, 600], 600), null)
})

test('I moves the start to now but never past the end', () => {
  assert.deepEqual(applyMark('start', [10, 40], 20, 600), [20, 40])
  assert.deepEqual(applyMark('start', [10, 40], 90, 600), [39, 40])
  assert.deepEqual(applyMark('start', [10, 40], -5, 600), [0, 40])
})

test('O moves the end to now but never before the start', () => {
  assert.deepEqual(applyMark('end', [10, 40], 30, 600), [10, 30])
  assert.deepEqual(applyMark('end', [10, 40], 5, 600), [10, 11])
  assert.deepEqual(applyMark('end', [10, 40], 900, 600), [10, 600])
})

test('marking near the video end keeps the minimum length inside the video', () => {
  assert.deepEqual(applyMark('start', [590, 600], 600, 600), [599, 600])
})

test('a new range is ten seconds each side of now, clamped to the video', () => {
  assert.deepEqual(newRangeAround(100, 600), [90, 110])
  assert.deepEqual(newRangeAround(3, 600), [0, 13])
  assert.deepEqual(newRangeAround(598, 600), [588, 600])
})

test('tick spacing grows with the visible span and keeps the count small', () => {
  assert.equal(tickStep(60), 10)
  assert.equal(tickStep(600), 60)
  assert.equal(tickStep(1500), 300)
  assert.equal(tickStep(5400), 600)
  for (const span of [30, 90, 400, 1500, 3000, 7200]) assert.ok(span / tickStep(span) <= 12)
})

test('panning a zoomed view keeps its width and stops at the video edges', () => {
  assert.deepEqual(panView([100, 160], 20, 600), [120, 180])
  assert.deepEqual(panView([100, 160], -500, 600), [0, 60])
  assert.deepEqual(panView([100, 160], 900, 600), [540, 600])
})

test('zooming in halves the visible span around the center and zooming out doubles it', () => {
  assert.deepEqual(zoomBy([0, 1200], 0.5, 300, 1200), [150, 750])
  assert.deepEqual(zoomBy([100, 200], 0.5, 150, 1200), [125, 175])
  assert.deepEqual(zoomBy([100, 200], 2, 150, 1200), [50, 250])
})

test('zoom keeps at least ten seconds, stays inside the video and returns null when fully zoomed out', () => {
  assert.deepEqual(zoomBy([100, 120], 0.25, 110, 1200), [105, 115])
  assert.deepEqual(zoomBy([0, 100], 2, 10, 1200), [0, 200])
  assert.deepEqual(zoomBy([1100, 1200], 2, 1190, 1200), [1000, 1200])
  assert.equal(zoomBy([100, 700], 2, 400, 1200), null)
})

test('a candidate counts as modified when its range differs from what was saved (or detected, if never saved)', () => {
  const base = c('a', 10, 40)
  assert.equal(rangeModified(base, 600), false)
  assert.equal(rangeModified(c('a', 10, 40, { user: { start: 12 } }), 600), true)
  assert.equal(rangeModified(c('a', 10, 40, { user: { start: 10, end: 40 } }), 600), false)
  const saved = c('a', 10, 40, { user: { start: 5, end: 50, savedClipId: 'a', savedStart: 5, savedEnd: 50 } })
  assert.equal(rangeModified(saved, 600), false)
  assert.equal(rangeModified({ ...saved, user: { ...saved.user, end: 60 } }, 600), true)
})

test('풀영상이 없어 길이를 모를 때(0)는 범위를 깎지 않으므로 고친 것으로 보지 않는다', () => {
  assert.equal(rangeModified(c('a', 199, 240), 0), false)
  assert.equal(rangeModified(c('a', 199, 240, { user: { savedClipId: 'a' } }), 0), false)
})
