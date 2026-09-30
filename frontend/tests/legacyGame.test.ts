import assert from 'node:assert/strict'
import test from 'node:test'

import { clipsOfGame, isLegacyWithoutVideo, rebuildStatusText } from '../src/legacyGame.ts'

const clip = (id: string, matchStartUtc: string, sessionDir: string, videoOffsetSec: number) => ({
  id,
  matchStartUtc,
  sessionDir,
  videoOffsetSec,
})

test('clipsOfGame keeps only the clips of that game, in the order they happened', () => {
  const game = { matchStartUtc: '2026-09-28T16:00:25.975000Z', sessionDir: 'bg_1' }
  const clips = [
    clip('b', '2026-09-28T16:00:25.975000Z', 'bg_1', 300),
    clip('x', '2026-09-28T16:19:12Z', 'bg_1', 10),
    clip('y', '2026-09-28T16:00:25.975000Z', 'bg_other', 5),
    clip('a', '2026-09-28T16:00:25.975000Z', 'bg_1', 100),
  ]
  assert.deepEqual(clipsOfGame(clips, game).map((c) => c.id), ['a', 'b'])
})

test('clipsOfGame finds nothing when the game has no start time', () => {
  assert.deepEqual(clipsOfGame([clip('a', '', 'bg_1', 1)], { matchStartUtc: null, sessionDir: 'bg_1' }), [])
})

test('the old-game panel is only for legacy games that have no full video', () => {
  assert.equal(isLegacyWithoutVideo({ legacy: true, hasFullVideo: false }), true)
  assert.equal(isLegacyWithoutVideo({ legacy: true, hasFullVideo: true }), false)
  assert.equal(isLegacyWithoutVideo({ legacy: false, hasFullVideo: false }), false)
  assert.equal(isLegacyWithoutVideo({ hasFullVideo: false }), false)
})

test('rebuild status text shows progress, done and the failure reason', () => {
  assert.equal(rebuildStatusText({ state: 'idle', message: '', fraction: 0 }), null)
  assert.equal(rebuildStatusText({ state: 'running', message: '', fraction: 0.456 }), '풀영상을 만드는 중… 46%')
  assert.equal(rebuildStatusText({ state: 'done', message: '', fraction: 1 }), '풀영상을 만들었습니다')
  assert.equal(rebuildStatusText({ state: 'error', message: '원본이 삭제됨', fraction: 0 }), '원본이 삭제됨')
})
