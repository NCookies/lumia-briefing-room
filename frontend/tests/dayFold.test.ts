import assert from 'node:assert/strict'
import test from 'node:test'

import {
  allCollapsed,
  collapseAll,
  dayAnchorId,
  loadCollapsed,
  revealDay,
  saveCollapsed,
  shortcutDays,
  toggleDay,
  visibleCollapsed,
} from '../src/dayFold.ts'

function memoryStorage(initial: Record<string, string> = {}) {
  const data = { ...initial }
  return {
    getItem: (k: string) => (k in data ? data[k] : null),
    setItem: (k: string, v: string) => {
      data[k] = v
    },
    data,
  }
}

test('collapsed days are remembered per tab and round-trip', () => {
  const store = memoryStorage()
  saveCollapsed('steam', new Set(['2026-09-29', 'unknown']), store)
  saveCollapsed('vod', new Set(['2026-09-01']), store)
  assert.deepEqual([...loadCollapsed('steam', store)].sort(), ['2026-09-29', 'unknown'])
  assert.deepEqual([...loadCollapsed('vod', store)], ['2026-09-01'])
})

test('nothing saved, broken data or a throwing storage all mean nothing is collapsed', () => {
  assert.equal(loadCollapsed('steam', memoryStorage()).size, 0)
  assert.equal(loadCollapsed('steam', memoryStorage({ 'lumia.collapsedDays.steam': '{oops' })).size, 0)
  assert.equal(loadCollapsed('steam', memoryStorage({ 'lumia.collapsedDays.steam': '"x"' })).size, 0)
  const throwing = {
    getItem: () => {
      throw new Error('blocked')
    },
    setItem: () => {
      throw new Error('blocked')
    },
  }
  assert.equal(loadCollapsed('steam', throwing).size, 0)
  assert.doesNotThrow(() => saveCollapsed('steam', new Set(['a']), throwing))
})

test('a day that was never collapsed (a new day) is expanded', () => {
  const collapsed = new Set(['2026-09-28'])
  assert.equal(collapsed.has('2026-09-30'), false)
})

test('toggleDay flips one day without touching the given set', () => {
  const start = new Set(['a'])
  assert.deepEqual([...toggleDay(start, 'b')].sort(), ['a', 'b'])
  assert.deepEqual([...toggleDay(start, 'a')], [])
  assert.deepEqual([...start], ['a'])
  assert.deepEqual([...toggleDay(new Set(), null)], ['unknown'])
})

test('collapseAll / allCollapsed use the days currently shown', () => {
  const days = ['2026-09-30', '2026-09-29', null]
  const all = collapseAll(days)
  assert.deepEqual([...all].sort(), ['2026-09-29', '2026-09-30', 'unknown'])
  assert.equal(allCollapsed(days, all), true)
  assert.equal(allCollapsed(days, new Set(['2026-09-30'])), false)
  assert.equal(allCollapsed([], new Set()), false)
})

test('revealDay expands a collapsed target and leaves the others collapsed', () => {
  const next = revealDay(new Set(['2026-09-29', '2026-09-28']), '2026-09-29')
  assert.deepEqual([...next], ['2026-09-28'])
  assert.deepEqual([...revealDay(new Set(['2026-09-28']), '2026-09-30')], ['2026-09-28'])
})

test('shortcuts follow the list order, use short dates and keep the unknown day last', () => {
  const list = shortcutDays(['2026-09-30', '2026-09-27', null])
  assert.deepEqual(list.map((s) => s.label), ['9/30', '9/27', '날짜 모름'])
  assert.deepEqual(list.map((s) => s.anchor), [
    dayAnchorId('steam', '2026-09-30'),
    dayAnchorId('steam', '2026-09-27'),
    dayAnchorId('steam', null),
  ])
})

test('anchor ids differ between tabs so both lists can stay mounted', () => {
  assert.notEqual(dayAnchorId('steam', '2026-09-30'), dayAnchorId('vod', '2026-09-30'))
  assert.equal(dayAnchorId('vod', null), 'day-vod-unknown')
})

test('검색 중에는 접어 둔 날짜도 펼쳐 보이고, 저장된 접힘은 그대로 둔다', () => {
  const collapsed = new Set(['2026-09-30'])
  assert.deepEqual([...visibleCollapsed(collapsed, true)], [])
  assert.equal(visibleCollapsed(collapsed, false), collapsed)
  assert.deepEqual([...collapsed], ['2026-09-30'])
})
