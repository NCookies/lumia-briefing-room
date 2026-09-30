import assert from 'node:assert/strict'
import test from 'node:test'

import type { Candidate } from '../src/games.ts'
import {
  applyMark,
  barPct,
  candidateAtTime,
  candidateAtBar,
  newRangeAround,
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
