import assert from 'node:assert/strict'
import test from 'node:test'

import { formatRoute, initialRoute, listRoute, parseRoute, rememberRoute, shouldHistoryBack } from '../src/route.ts'

test('formatRoute builds hash addresses per screen', () => {
  assert.equal(formatRoute({ tab: 'steam' }), '#/steam')
  assert.equal(formatRoute({ tab: 'vod' }), '#/vod')
  assert.equal(formatRoute({ tab: 'library' }), '#/clips')
  assert.equal(formatRoute({ tab: 'admin' }), '#/admin')
  assert.equal(formatRoute({ tab: 'steam', game: '20260930_231500' }), '#/steam/game/20260930_231500')
  assert.equal(formatRoute({ tab: 'vod', game: 'v1-g2' }), '#/vod/game/v1-g2')
  assert.equal(formatRoute({ tab: 'library', category: '자동 보관' }), `#/clips/${encodeURIComponent('자동 보관')}`)
})

test('parseRoute reads back what formatRoute wrote', () => {
  const routes = [
    { tab: 'steam' as const },
    { tab: 'vod' as const },
    { tab: 'library' as const },
    { tab: 'admin' as const },
    { tab: 'steam' as const, game: 'a/b c' },
    { tab: 'vod' as const, game: 'x' },
    { tab: 'library' as const, category: '내 하이라이트/1' },
  ]
  for (const r of routes) assert.deepEqual(parseRoute(formatRoute(r)), r)
})

test('parseRoute returns null for empty or unknown hashes', () => {
  assert.equal(parseRoute(''), null)
  assert.equal(parseRoute('#'), null)
  assert.equal(parseRoute('#/'), null)
  assert.equal(parseRoute('#/nowhere'), null)
  assert.equal(parseRoute('#/clips/%E0%A4%A'), null)
})

test('parseRoute ignores a game segment on tabs without viewers and an empty game key', () => {
  assert.deepEqual(parseRoute('#/clips/game/x'), { tab: 'library', category: 'game/x' })
  assert.deepEqual(parseRoute('#/steam/game/'), { tab: 'steam' })
  assert.deepEqual(parseRoute('#/steam/other'), { tab: 'steam' })
  assert.deepEqual(parseRoute('#/admin/anything'), { tab: 'admin' })
})

test('initialRoute prefers the address, then the remembered tab', () => {
  assert.deepEqual(initialRoute('#/vod/game/k', 'steam'), { tab: 'vod', game: 'k' })
  assert.deepEqual(initialRoute('', 'library'), { tab: 'library' })
  assert.deepEqual(initialRoute('#/bogus', 'vod'), { tab: 'vod' })
})

test('listRoute drops the open game and keeps the tab', () => {
  assert.deepEqual(listRoute({ tab: 'steam', game: 'g' }), { tab: 'steam' })
  assert.deepEqual(listRoute({ tab: 'library', category: 'c' }), { tab: 'library', category: 'c' })
})

test('shouldHistoryBack only when the previous entry is exactly the target', () => {
  assert.equal(shouldHistoryBack('#/steam', { tab: 'steam' }), true)
  assert.equal(shouldHistoryBack('#/clips', { tab: 'steam' }), false)
  assert.equal(shouldHistoryBack(undefined, { tab: 'steam' }), false)
})

test('rememberRoute keeps the last route per tab', () => {
  let memo = rememberRoute({}, { tab: 'steam', game: 'g' })
  memo = rememberRoute(memo, { tab: 'library', category: 'c' })
  assert.deepEqual(memo.steam, { tab: 'steam', game: 'g' })
  assert.deepEqual(memo.library, { tab: 'library', category: 'c' })
  assert.equal(memo.vod, undefined)
})

test('a clip address is #/clips/<category>/clip/<clip> and reads back', () => {
  const route = { tab: 'library' as const, category: '내 하이라이트', clip: 'clip 01' }
  assert.equal(formatRoute(route), `#/clips/${encodeURIComponent('내 하이라이트')}/clip/${encodeURIComponent('clip 01')}`)
  assert.deepEqual(parseRoute(formatRoute(route)), route)
  assert.deepEqual(parseRoute('#/clips/a%2Fb/clip/c'), { tab: 'library', category: 'a/b', clip: 'c' })
})

test('a clip needs a category and an empty clip segment falls back to the category list', () => {
  assert.equal(formatRoute({ tab: 'library', clip: 'x' }), '#/clips')
  assert.deepEqual(parseRoute('#/clips/a/clip/'), { tab: 'library', category: 'a/clip/' })
  assert.deepEqual(parseRoute('#/clips/clip/x'), { tab: 'library', category: 'clip/x' })
})

test('a game address can carry the selected candidate', () => {
  const route = { tab: 'steam' as const, game: '20260930_231500', cand: '20260930_231500_02' }
  assert.equal(formatRoute(route), '#/steam/game/20260930_231500/cand/20260930_231500_02')
  assert.deepEqual(parseRoute(formatRoute(route)), route)
  assert.deepEqual(parseRoute('#/vod/game/k/cand/'), { tab: 'vod', game: 'k' })
  assert.equal(formatRoute({ tab: 'steam', cand: 'x' }), '#/steam')
})

test('listRoute of a clip goes back to its category, of a game to the tab list', () => {
  assert.deepEqual(listRoute({ tab: 'library', category: 'c', clip: 'x' }), { tab: 'library', category: 'c' })
  assert.deepEqual(listRoute({ tab: 'steam', game: 'g', cand: 'c' }), { tab: 'steam' })
})
