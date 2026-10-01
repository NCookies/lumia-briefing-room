import assert from 'node:assert/strict'
import test from 'node:test'

import { CLIP_VIEWER_ACTIONS, clipViewerAction, idAfterRemoval, neighborClipId, rangeFixTarget } from '../src/clipViewer.ts'
import { VIEWER_SHORTCUTS, shortcutGroupsFor } from '../src/viewerShortcuts.ts'

test('prev/next follow the list order and stop at both ends', () => {
  const ids = ['a', 'b', 'c']
  assert.equal(neighborClipId(ids, 'b', 'next'), 'c')
  assert.equal(neighborClipId(ids, 'b', 'prev'), 'a')
  assert.equal(neighborClipId(ids, 'c', 'next'), null)
  assert.equal(neighborClipId(ids, 'a', 'prev'), null)
  assert.equal(neighborClipId(ids, 'zzz', 'next'), null)
  assert.equal(neighborClipId([], 'a', 'next'), null)
})

test('after removing a clip the next one is shown, else the previous, else the list', () => {
  assert.equal(idAfterRemoval(['a', 'b', 'c'], 'b'), 'c')
  assert.equal(idAfterRemoval(['a', 'b', 'c'], 'c'), 'b')
  assert.equal(idAfterRemoval(['a'], 'a'), null)
  assert.equal(idAfterRemoval(['a', 'b'], 'zzz'), null)
})

test('only the playback, move, delete, category, memo and help keys reach the clip screen', () => {
  assert.equal(clipViewerAction('togglePlay'), 'togglePlay')
  assert.equal(clipViewerAction('prevClip'), 'prevClip')
  assert.equal(clipViewerAction('nextClip'), 'nextClip')
  assert.equal(clipViewerAction('deleteClip'), 'deleteClip')
  assert.equal(clipViewerAction('archivePopup'), 'archivePopup')
  assert.equal(clipViewerAction('memo'), 'memo')
  for (const range of ['markStart', 'markEnd', 'addSection', 'undo', 'redo'] as const) assert.equal(clipViewerAction(range), null)
  assert.equal(clipViewerAction(null), null)
})

test('the clip screen shortcut table lists exactly the keys it handles', () => {
  const groups = shortcutGroupsFor(CLIP_VIEWER_ACTIONS)
  const descs = groups.flatMap((g) => g.rows.map((r) => r.desc))
  assert.equal(descs.length, VIEWER_SHORTCUTS.filter((s) => CLIP_VIEWER_ACTIONS.includes(s.action)).length)
  assert.ok(!groups.some((g) => g.title === '범위 편집'))
  assert.ok(groups.some((g) => g.rows.some((r) => r.keys === 'Ctrl+←')))
})

test('a clip made from a game opens that game with the candidate selected', () => {
  assert.deepEqual(rangeFixTarget({ gameKey: '20260930_231500', candidateId: '20260930_231500_02', source: 'steam', hasFullVideo: true }), {
    kind: 'game',
    tab: 'steam',
    gameKey: '20260930_231500',
    candidateId: '20260930_231500_02',
  })
  assert.deepEqual(rangeFixTarget({ gameKey: 'vod_x_g01', candidateId: 'vod_x_g01_01', source: 'vod', hasFullVideo: true }), {
    kind: 'game',
    tab: 'vod',
    gameKey: 'vod_x_g01',
    candidateId: 'vod_x_g01_01',
  })
})

test('clips without a linked game or without its full video fall back to trimming', () => {
  assert.deepEqual(rangeFixTarget(null), { kind: 'trim' })
  assert.deepEqual(rangeFixTarget({ gameKey: 'g', candidateId: 'c', source: 'steam', hasFullVideo: false }), { kind: 'trim' })
})
