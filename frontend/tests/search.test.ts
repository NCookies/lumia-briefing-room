import assert from 'node:assert/strict'
import test from 'node:test'

import { SEARCH_DEBOUNCE_MS, isSearching, matchLabel, matchesQuery, normalizeQuery } from '../src/search.ts'

test('디바운스는 옛 제목 검색과 같은 0.3초', () => {
  assert.equal(SEARCH_DEBOUNCE_MS, 300)
})

test('대소문자·모든 공백을 무시한 부분 일치', () => {
  assert.equal(normalizeQuery(' Hello  World\t'), 'helloworld')
  assert.equal(matchesQuery('마지막 교전', '교 전'), true)
  assert.equal(matchesQuery('FINAL Fight', 'al fi'), true)
  assert.equal(matchesQuery('마지막 교전', '우승'), false)
})

test('빈 검색어는 검색이 아니다: 아무것도 맞지 않고 isSearching 이 거짓', () => {
  assert.equal(isSearching('   '), false)
  assert.equal(isSearching(' a'), true)
  assert.equal(matchesQuery('아무거나', '  '), false)
  assert.equal(matchesQuery(null, 'a'), false)
  assert.equal(matchesQuery(undefined, 'a'), false)
})

test('찾은 곳 한 줄: "후보 \'…\'", 긴 글자는 줄여 보인다', () => {
  assert.equal(matchLabel({ where: '후보', text: '마지막 교전' }), "후보 '마지막 교전'")
  assert.equal(matchLabel({ where: '메모', text: '가'.repeat(60) }), `메모 '${'가'.repeat(30)}…'`)
  assert.equal(matchLabel({ where: '메모', text: '줄1\n줄2' }), "메모 '줄1 줄2'")
  assert.equal(matchLabel(null), '')
})
