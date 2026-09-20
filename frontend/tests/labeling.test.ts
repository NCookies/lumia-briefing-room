import assert from 'node:assert/strict'
import test from 'node:test'

import {
  applyLabel,
  labelForKey,
  nextUnlabeledIndex,
  progress,
  scorePercent,
  scoreTone,
} from '../src/labeling.ts'

const clip = (id: string, userLabel: 'pvp' | 'pve' | null = null) => ({ id, userLabel })

test('labelForKey maps 1/2 to labels and 0/Backspace to clearing', () => {
  assert.equal(labelForKey('1'), 'pvp')
  assert.equal(labelForKey('2'), 'pve')
  assert.equal(labelForKey('0'), null)
  assert.equal(labelForKey('Backspace'), null)
})

test('labelForKey ignores every other key', () => {
  assert.equal(labelForKey('a'), undefined)
  assert.equal(labelForKey('ArrowRight'), undefined)
  assert.equal(labelForKey('3'), undefined)
})

test('applyLabel changes only the matching clip and does not mutate', () => {
  const clips = [clip('a'), clip('b')]

  const next = applyLabel(clips, 'b', 'pvp')

  assert.deepEqual(next, [clip('a'), clip('b', 'pvp')])
  assert.equal(clips[1].userLabel, null)
  assert.equal(next[0], clips[0])
})

test('applyLabel can clear a label', () => {
  assert.deepEqual(applyLabel([clip('a', 'pve')], 'a', null), [clip('a')])
})

test('nextUnlabeledIndex finds the next unlabeled clip after the current one', () => {
  const clips = [clip('a'), clip('b', 'pvp'), clip('c'), clip('d')]

  assert.equal(nextUnlabeledIndex(clips, 0), 2)
  assert.equal(nextUnlabeledIndex(clips, 2), 3)
})

test('nextUnlabeledIndex wraps around to earlier unlabeled clips', () => {
  const clips = [clip('a'), clip('b', 'pvp'), clip('c', 'pve')]

  assert.equal(nextUnlabeledIndex(clips, 2), 0)
})

test('nextUnlabeledIndex returns null when everything is labeled', () => {
  assert.equal(nextUnlabeledIndex([clip('a', 'pvp'), clip('b', 'pve')], 0), null)
  assert.equal(nextUnlabeledIndex([], 0), null)
})

test('progress counts labeled clips', () => {
  assert.deepEqual(progress([clip('a', 'pvp'), clip('b'), clip('c', 'pve')]), { labeled: 2, total: 3 })
  assert.deepEqual(progress([]), { labeled: 0, total: 0 })
})

test('scorePercent formats a 0-1 score and shows a dash when unscored', () => {
  assert.equal(scorePercent(1), '100%')
  assert.equal(scorePercent(0.35), '35%')
  assert.equal(scorePercent(0), '0%')
  assert.equal(scorePercent(null), '-')
  assert.equal(scorePercent(undefined), '-')
})

test('scoreTone separates confirmed, likely, weak and none', () => {
  assert.equal(scoreTone(1), 'confirmed')
  assert.equal(scoreTone(0.5), 'likely')
  assert.equal(scoreTone(0.2), 'weak')
  assert.equal(scoreTone(0), 'none')
  assert.equal(scoreTone(null), 'none')
})
