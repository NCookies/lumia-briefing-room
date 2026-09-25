import assert from 'node:assert/strict'
import test from 'node:test'

import { emptyStateKind } from '../src/emptyState.ts'

const base = { source: 'steam', loading: false, error: false, empty: true, trashed: false, filtered: false, vodTotal: 0 } as const

test('nothing is shown while loading, on error, or when there is something to list', () => {
  assert.equal(emptyStateKind({ ...base, loading: true }), 'none')
  assert.equal(emptyStateKind({ ...base, error: true }), 'none')
  assert.equal(emptyStateKind({ ...base, empty: false }), 'none')
})

test('the trash view says it is empty and offers nothing else', () => {
  assert.equal(emptyStateKind({ ...base, trashed: true }), 'trash')
  assert.equal(emptyStateKind({ ...base, source: 'vod', trashed: true }), 'trash')
})

test('a filter that hides everything is reported before the first-use hints', () => {
  assert.equal(emptyStateKind({ ...base, filtered: true }), 'filter')
  assert.equal(emptyStateKind({ ...base, source: 'vod', filtered: true, vodTotal: 2 }), 'filter')
})

test('steam tab without clips offers the backfill analysis', () => {
  assert.equal(emptyStateKind(base), 'steam')
})

test('video tab without any registered video asks to add a path', () => {
  assert.equal(emptyStateKind({ ...base, source: 'vod', vodTotal: 0 }), 'vod-no-sources')
})

test('video tab whose videos all have no clips says so instead of asking for paths', () => {
  assert.equal(emptyStateKind({ ...base, source: 'vod', vodTotal: 3 }), 'vod-no-clips')
})
