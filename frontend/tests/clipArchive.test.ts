import assert from 'node:assert/strict'
import test from 'node:test'

import { cardHeadline, flattenGroups, searchResultLabel, sortedForCategory, sortedGroups } from '../src/clipArchive.ts'

const clip = (over: Record<string, unknown> = {}) => ({
  id: 'a',
  title: '교전 하나',
  fileName: 'a.mp4',
  matchStartUtc: '2026-09-30T00:24:00Z',
  matchResult: { placement: 1, matchType: 'rank' },
  ...over,
})

test('카드 머리글은 순위와 일반/랭크, 결과를 모르면 결과 미확인', () => {
  assert.equal(cardHeadline(clip()), '#1 · 랭크')
  assert.equal(cardHeadline(clip({ matchResult: { placement: 7, matchType: 'normal' } })), '#7 · 일반')
  assert.equal(cardHeadline(clip({ matchResult: null })), '결과 미확인')
  assert.equal(cardHeadline(clip({ matchResult: { outcome: '승리' }, gameMode: 'cobalt' })), '승리')
})

test('검색 결과는 카테고리 묶음마다 게임 시각 최신순이고, 묶음 순서는 서버가 준 그대로', () => {
  const groups = [
    { name: '보관함', clips: [clip({ id: 'old', matchStartUtc: '2026-09-28T00:00:00Z' }), clip({ id: 'new', matchStartUtc: '2026-09-30T00:00:00Z' })] },
    { name: '자동 보관', clips: [clip({ id: 'x' })] },
  ]
  const sorted = sortedGroups(groups)
  assert.deepEqual(sorted.map((g) => g.name), ['보관함', '자동 보관'])
  assert.deepEqual(sorted[0].clips.map((c) => c.id), ['new', 'old'])
  assert.deepEqual(flattenGroups(sorted).map((c) => c.id), ['new', 'old', 'x'])
})

test('검색 결과 개수 문구', () => {
  assert.equal(searchResultLabel([]), '검색 결과 0개')
  assert.equal(searchResultLabel([{ name: 'a', clips: [clip(), clip()] }, { name: 'b', clips: [clip()] }]), '검색 결과 3개 · 카테고리 2곳')
})

test('클립은 게임 시각 최신순, 시각이 없으면 뒤로', () => {
  const list = [
    clip({ id: 'old', matchStartUtc: '2026-09-28T00:00:00Z' }),
    clip({ id: 'none', matchStartUtc: undefined }),
    clip({ id: 'new', matchStartUtc: '2026-09-30T00:00:00Z' }),
  ]
  assert.deepEqual(sortedForCategory(list).map((c) => c.id), ['new', 'old', 'none'])
})
