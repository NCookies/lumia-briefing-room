import assert from 'node:assert/strict'
import test from 'node:test'

import { deleteMenuItems, deleteWarning, mustAskBeforeDelete, type DeletableGame } from '../src/gameDelete.ts'

const game = (extra: Partial<DeletableGame> = {}): DeletableGame => ({
  hasFullVideo: true,
  fullVideoSizeBytes: 4 * 1024 ** 3,
  savedClipCount: 3,
  autoClipCount: 2,
  pinned: false,
  ...extra,
})

test('메뉴 세 항목 - 풀영상만·자동 보관 클립만·게임 전체(풀영상과 클립 전체는 게임 전체 삭제에 포함돼 따로 없다)', () => {
  const items = deleteMenuItems(game())
  assert.deepEqual(items.map((i) => [i.target, i.label, i.disabled]), [
    ['fullVideo', '풀영상만 삭제', false],
    ['clips', '자동 보관 클립 삭제', false],
    ['all', '게임 전체 삭제', false],
  ])
})

test('풀영상이 없으면 풀영상만 삭제는 꺼지고, 자동 보관 클립이 없으면 클립 삭제가 꺼진다', () => {
  const noVideo = deleteMenuItems(game({ hasFullVideo: false }))
  assert.equal(noVideo[0].disabled, true)
  assert.equal(noVideo[2].disabled, false, '게임 전체 삭제는 늘 켜져 있다')
  const noClips = deleteMenuItems(game({ autoClipCount: 0 }))
  assert.equal(noClips[1].disabled, true)
  assert.equal(noClips[2].disabled, false)
  const nothing = deleteMenuItems(game({ hasFullVideo: false, autoClipCount: 0 }))
  assert.deepEqual(nothing.map((i) => i.disabled), [true, true, false], '지울 게 없어도 게임 기록까지 지우는 항목은 켜져 있다')
})

test('게임 전체 삭제 경고는 기록까지 지워진다고 알리고 고정한 게임은 한 줄 더', () => {
  const text = deleteWarning(game(), 'all')
  assert.match(text, /목록에서 완전히 삭제/)
  assert.match(text, /풀영상/)
  assert.match(text, /클립 3개/)
  assert.match(text, /게임 기록/)
  assert.match(deleteWarning(game({ pinned: true }), 'all'), /고정한 게임입니다/)
  assert.doesNotMatch(deleteWarning(game({ hasFullVideo: false, savedClipCount: 0 }), 'all'), /풀영상|클립/)
})

test('경고 창에는 지워질 풀영상 크기와 자동 보관 클립 수, 남는 보관 클립 수를 적는다', () => {
  assert.match(deleteWarning(game(), 'fullVideo'), /풀영상 4\.00 GB/)
  assert.doesNotMatch(deleteWarning(game(), 'fullVideo'), /클립/)
  const clips = deleteWarning(game(), 'clips')
  assert.match(clips, /자동 보관 클립 2개을\(를\) 삭제합니다/)
  assert.match(clips, /보관한 클립 3개는 남습니다/)
  const both = deleteWarning(game(), 'both')
  assert.match(both, /풀영상 4\.00 GB/)
  assert.match(both, /자동 보관 클립 2개/)
  assert.match(both, /보관한 클립 3개는 남습니다/)
})

test('보관한 클립이 없으면 남는다는 말을 하지 않는다', () => {
  assert.doesNotMatch(deleteWarning(game({ savedClipCount: 0 }), 'clips'), /보관한 클립/)
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
