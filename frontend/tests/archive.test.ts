import assert from 'node:assert/strict'
import test from 'node:test'

import { popupRows, rowState } from '../src/archive.ts'
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

test('보관 상태: 클립이 없거나 자동 보관에 있으면 보관 전, 카테고리에 있으면 보관됨', () => {
  assert.deepEqual(rowState(false, false, false), { bookmark: 'none', resave: false, deletable: false })
  assert.deepEqual(rowState(true, false, false), { bookmark: 'none', resave: false, deletable: true })
  assert.deepEqual(rowState(true, true, false), { bookmark: 'archived', resave: false, deletable: true })
})

test('범위를 고친 클립은 보관됨 여부와 상관없이 다시 저장이 필요하고, 클립이 없으면 필요 없다', () => {
  assert.equal(rowState(true, true, true).resave, true)
  assert.equal(rowState(true, false, true).resave, true)
  assert.equal(rowState(false, false, true).resave, false)
})
