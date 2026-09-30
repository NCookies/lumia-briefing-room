import assert from 'node:assert/strict'
import test from 'node:test'

import { archiveState, popupRows } from '../src/archive.ts'
import type { Category } from '../src/categoriesApi.ts'

const cat = (name: string, extra: Partial<Category> = {}): Category => ({
  name,
  auto: false,
  default: false,
  clipCount: 0,
  thumbnailClipId: null,
  ...extra,
})

const cats = [cat('보관함', { default: true, clipCount: 2 }), cat('아야'), cat('자동 보관', { auto: true, clipCount: 9 })]

test('자동 보관 칸도 항상 보이되 맨 아래에 흐리게', () => {
  assert.deepEqual(popupRows(cats, null).map((r) => [r.name, r.dim, r.selectable]), [
    ['보관함', false, true],
    ['아야', false, true],
    ['자동 보관', true, true],
  ])
  assert.deepEqual(popupRows(cats, '자동 보관').map((r) => r.checked), [false, false, true])
})

test('지금 있는 카테고리에 체크가 붙는다', () => {
  assert.deepEqual(popupRows(cats, '아야').map((r) => r.checked), [false, true, false])
})

test('보관 상태: 안 함 / 보관됨 / 범위를 고쳐 저장 대기', () => {
  assert.equal(archiveState(false, false), 'none')
  assert.equal(archiveState(false, true), 'none')
  assert.equal(archiveState(true, false), 'archived')
  assert.equal(archiveState(true, true), 'pending')
})
