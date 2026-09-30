import assert from 'node:assert/strict'
import test from 'node:test'

import { cardHeadline, filterClips, sortedForCategory } from '../src/clipArchive.ts'

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

test('검색은 제목·파일 이름을 대소문자 없이 거른다', () => {
  const list = [clip({ id: '1', title: '아야 궁극기' }), clip({ id: '2', title: '사냥', fileName: 'Hunt.mp4' })]
  assert.deepEqual(filterClips(list, '궁극').map((c) => c.id), ['1'])
  assert.deepEqual(filterClips(list, 'hunt').map((c) => c.id), ['2'])
  assert.deepEqual(filterClips(list, '  ').map((c) => c.id), ['1', '2'])
})

test('클립은 게임 시각 최신순, 시각이 없으면 뒤로', () => {
  const list = [
    clip({ id: 'old', matchStartUtc: '2026-09-28T00:00:00Z' }),
    clip({ id: 'none', matchStartUtc: undefined }),
    clip({ id: 'new', matchStartUtc: '2026-09-30T00:00:00Z' }),
  ]
  assert.deepEqual(sortedForCategory(list).map((c) => c.id), ['new', 'old', 'none'])
})
