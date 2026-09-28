import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildCobaltPhaseColumns,
  buildPhaseColumns,
  elapsedGameSec,
  estimatePhaseIndex,
  phaseLabel,
  PHASE_LENGTH_SEC,
} from '../src/timeline.ts'

test('phaseLabel counts days from 1 with day then night', () => {
  assert.equal(phaseLabel(0), '1일차 낮')
  assert.equal(phaseLabel(1), '1일차 밤')
  assert.equal(phaseLabel(4), '3일차 낮')
})

test('buildPhaseColumns keeps empty phases between the first phase and the last clip', () => {
  const cols = buildPhaseColumns([
    { id: 'a', phaseIndex: 1 },
    { id: 'b', phaseIndex: 4 },
    { id: 'c', phaseIndex: 4 },
  ])
  assert.deepEqual(
    cols.map((c) => [c.phaseIndex, c.clips.length]),
    [[0, 0], [1, 1], [2, 0], [3, 0], [4, 2]],
  )
})

test('buildPhaseColumns marks the free revive zone up to phase 3 and the credit zone after it', () => {
  const cols = buildPhaseColumns([{ phaseIndex: 4 }])
  assert.deepEqual(cols.map((c) => c.zone), ['free', 'free', 'free', 'free', 'credit'])
})

test('buildPhaseColumns puts clips without a phase in a trailing unknown column', () => {
  const cols = buildPhaseColumns([{ phaseIndex: null }, { phaseIndex: 0 }])
  assert.deepEqual(cols.map((c) => c.label), ['1일차 낮', '시점 알 수 없음'])
  assert.equal(cols[1].zone, null)
  assert.equal(buildPhaseColumns([{ phaseIndex: null }]).length, 1)
  assert.deepEqual(buildPhaseColumns([]), [])
})

test('estimatePhaseIndex divides elapsed time by the phase length, clamped at 0', () => {
  assert.equal(estimatePhaseIndex(0, 165), 0)
  assert.equal(estimatePhaseIndex(164, 165), 0)
  assert.equal(estimatePhaseIndex(165, 165), 1)
  assert.equal(estimatePhaseIndex(500, 165), 3)
  assert.equal(estimatePhaseIndex(-10, 165), 0)
})

test('elapsedGameSec computes steam clips from sessionStartUtc + offset minus matchStartUtc', () => {
  const clip = {
    sessionStartUtc: '2026-09-20T10:00:00Z',
    matchStartUtc: '2026-09-20T10:01:00Z',
    combatStartOffsetSec: 90,
  }
  assert.equal(elapsedGameSec(clip), 30)
})

test('elapsedGameSec treats a missing source as steam', () => {
  const clip = {
    source: undefined,
    sessionStartUtc: '2026-09-20T10:00:00Z',
    matchStartUtc: '2026-09-20T10:00:00Z',
    combatStartOffsetSec: 42,
  }
  assert.equal(elapsedGameSec(clip), 42)
})

test('elapsedGameSec computes vod clips from combatStartOffsetSec minus gameStartOffsetSec', () => {
  const clip = { source: 'vod' as const, gameStartOffsetSec: 14820, combatStartOffsetSec: 15242 }
  assert.equal(elapsedGameSec(clip), 422)
})

test('elapsedGameSec is null when required fields are missing', () => {
  assert.equal(elapsedGameSec({}), null)
  assert.equal(elapsedGameSec({ combatStartOffsetSec: 10 }), null)
  assert.equal(elapsedGameSec({ source: 'vod', combatStartOffsetSec: 10 }), null)
  assert.equal(elapsedGameSec({ sessionStartUtc: 'not-a-date', matchStartUtc: 'also-not', combatStartOffsetSec: 1 }), null)
})

test('elapsedGameSec is null when the combat time is before the game start (bad data)', () => {
  const steamClip = {
    sessionStartUtc: '2026-09-20T10:00:00Z',
    matchStartUtc: '2026-09-20T10:05:00Z',
    combatStartOffsetSec: 10,
  }
  assert.equal(elapsedGameSec(steamClip), null)

  const vodClip = { source: 'vod' as const, gameStartOffsetSec: 100, combatStartOffsetSec: 50 }
  assert.equal(elapsedGameSec(vodClip), null)
})

test('buildPhaseColumns estimates a column from elapsedGameSec for clips without a read phaseIndex', () => {
  const cols = buildPhaseColumns([
    { id: 'a', phaseIndex: null, elapsedGameSec: 400 }, // 400/165 = phase 2
  ])
  assert.deepEqual(
    cols.map((c) => c.phaseIndex),
    [0, 1, 2],
  )
  assert.equal(cols[2].clips.length, 1)
  assert.equal(cols[2].clips[0].estimated, true)
  assert.equal((cols[2].clips[0].clip as { id: string }).id, 'a')
})

test('buildPhaseColumns keeps read phaseIndex clips unestimated and mixes them with estimated ones in the same column', () => {
  const cols = buildPhaseColumns([
    { id: 'known', phaseIndex: 2 },
    { id: 'estimated', phaseIndex: null, elapsedGameSec: 400 }, // also phase 2
  ])
  const phase2 = cols.find((c) => c.phaseIndex === 2)!
  assert.deepEqual(
    phase2.clips.map((e) => [(e.clip as { id: string }).id, e.estimated]),
    [
      ['known', false],
      ['estimated', true],
    ],
  )
})

test('buildPhaseColumns only falls back to the trailing unknown column when elapsed time cannot be computed', () => {
  const cols = buildPhaseColumns([
    { phaseIndex: 0 },
    { phaseIndex: null, elapsedGameSec: null },
    { phaseIndex: null },
  ])
  const last = cols[cols.length - 1]
  assert.equal(last.phaseIndex, null)
  assert.equal(last.clips.length, 2)
})

test('PHASE_LENGTH_SEC falls within the measured 2.5~3 minute range', () => {
  assert.ok(PHASE_LENGTH_SEC >= 150 && PHASE_LENGTH_SEC <= 180)
})

test('buildCobaltPhaseColumns labels columns by Phase number, no day/night or revive zone', () => {
  const cols = buildCobaltPhaseColumns([
    { id: 'a', cobaltPhase: 1 },
    { id: 'b', cobaltPhase: 3 },
    { id: 'c', cobaltPhase: 3 },
  ])
  assert.deepEqual(
    cols.map((c) => [c.label, c.clips.length, c.zone]),
    [['Phase 1', 1, null], ['Phase 2', 0, null], ['Phase 3', 2, null]],
  )
})

test('buildCobaltPhaseColumns puts clips without a phase in a trailing unknown column', () => {
  const cols = buildCobaltPhaseColumns([{ cobaltPhase: null }, { cobaltPhase: 1 }])
  assert.deepEqual(cols.map((c) => c.label), ['Phase 1', '시점 알 수 없음'])
  assert.equal(buildCobaltPhaseColumns([{ cobaltPhase: null }]).length, 1)
  assert.deepEqual(buildCobaltPhaseColumns([]), [])
})
