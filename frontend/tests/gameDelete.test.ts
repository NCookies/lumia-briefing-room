import assert from 'node:assert/strict'
import test from 'node:test'

import { deleteMenuItems, deleteWarning, mustAskBeforeDelete, type DeletableGame } from '../src/gameDelete.ts'

const game = (extra: Partial<DeletableGame> = {}): DeletableGame => ({
  hasFullVideo: true,
  fullVideoSizeBytes: 4 * 1024 ** 3,
  savedClipCount: 3,
  pinned: false,
  ...extra,
})

test('메뉴 세 항목 - 풀영상·클립이 있으면 모두 켜진다', () => {
  const items = deleteMenuItems(game())
  assert.deepEqual(items.map((i) => [i.target, i.label, i.disabled]), [
    ['fullVideo', '풀영상만 삭제', false],
    ['clips', '클립만 전체 삭제', false],
    ['both', '풀영상과 클립 전체 삭제', false],
  ])
})

test('풀영상이 없으면 풀영상만 삭제는 꺼지고, 클립이 없으면 클립만 삭제가 꺼진다', () => {
  const noVideo = deleteMenuItems(game({ hasFullVideo: false }))
  assert.equal(noVideo[0].disabled, true)
  assert.equal(noVideo[2].disabled, false)
  const noClips = deleteMenuItems(game({ savedClipCount: 0 }))
  assert.equal(noClips[1].disabled, true)
  assert.equal(noClips[2].disabled, false)
  const nothing = deleteMenuItems(game({ hasFullVideo: false, savedClipCount: 0 }))
  assert.equal(nothing.every((i) => i.disabled), true)
})

test('경고 창에는 지워질 풀영상 크기와 클립 수를 적는다', () => {
  assert.match(deleteWarning(game(), 'fullVideo'), /풀영상 4\.00 GB/)
  assert.doesNotMatch(deleteWarning(game(), 'fullVideo'), /클립/)
  assert.match(deleteWarning(game(), 'clips'), /클립 3개/)
  const both = deleteWarning(game(), 'both')
  assert.match(both, /풀영상 4\.00 GB/)
  assert.match(both, /클립 3개/)
})

test('풀영상이 없으면 both 경고에서 풀영상은 빠진다', () => {
  assert.doesNotMatch(deleteWarning(game({ hasFullVideo: false }), 'both'), /풀영상/)
})

test('고정한 게임이면 경고 창에 한 줄이 더 붙는다', () => {
  assert.match(deleteWarning(game({ pinned: true }), 'both'), /고정한 게임입니다/)
  assert.doesNotMatch(deleteWarning(game(), 'both'), /고정한 게임/)
})

test('다시 묻지 않기를 켰어도 고정한 게임은 묻는다', () => {
  assert.equal(mustAskBeforeDelete(game({ pinned: true }), false), true)
  assert.equal(mustAskBeforeDelete(game(), false), false)
  assert.equal(mustAskBeforeDelete(game(), true), true)
})
