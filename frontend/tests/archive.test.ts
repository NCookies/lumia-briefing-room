import assert from 'node:assert/strict'
import test from 'node:test'

import { initialHighlight, popupEntries, popupRows, rowState, stepHighlight } from '../src/archive.ts'
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

test('보관 위치 창의 키보드 칸: 카테고리 줄 + 새 카테고리, 보관 방식이 꺼졌으면 `보관하기` 한 칸이 맨 앞', () => {
  const rows = popupRows(cats, null)
  assert.deepEqual(popupEntries(rows, true), [{ kind: 'row', name: rows[0].name }, { kind: 'row', name: rows[1].name }, { kind: 'row', name: rows[2].name }, { kind: 'new' }])
  assert.deepEqual(popupEntries(rows, false), [{ kind: 'plain' }, ...rows.map((r) => ({ kind: 'row', name: r.name }))])
})

test('↑/↓ 는 끝에서 반대편으로 이어진다', () => {
  assert.equal(stepHighlight(0, 4, 1), 1)
  assert.equal(stepHighlight(3, 4, 1), 0)
  assert.equal(stepHighlight(0, 4, -1), 3)
  assert.equal(stepHighlight(0, 0, 1), 0)
})

test('처음 강조는 지금 보관된 카테고리, 없으면 첫 칸', () => {
  const entries = popupEntries(popupRows(cats, null), true)
  assert.equal(initialHighlight(entries, cats[1].name), 1)
  assert.equal(initialHighlight(entries, null), 0)
  assert.equal(initialHighlight(entries, '없는 이름'), 0)
})
