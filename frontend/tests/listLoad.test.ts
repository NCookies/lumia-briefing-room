import assert from 'node:assert/strict'
import test from 'node:test'

import { gameCountLabel, listLoading, returnedToList } from '../src/listLoad.ts'

test('the list counts as loading until both the videos and the games have arrived', () => {
  assert.equal(listLoading({ vodsLoaded: false, gamesLoaded: false }), true)
  assert.equal(listLoading({ vodsLoaded: true, gamesLoaded: false }), true)
  assert.equal(listLoading({ vodsLoaded: false, gamesLoaded: true }), true)
  assert.equal(listLoading({ vodsLoaded: true, gamesLoaded: true }), false)
})

test('a failed load stops the loading state so the error can be shown', () => {
  assert.equal(listLoading({ vodsLoaded: false, gamesLoaded: false, failed: true }), false)
})

test('the game count is not shown as 0 before the games have loaded', () => {
  assert.equal(gameCountLabel({ loaded: false, total: 0, shown: 0, dueOnly: false }), '게임 불러오는 중…')
  assert.equal(gameCountLabel({ loaded: true, total: 0, shown: 0, dueOnly: false }), '게임 0개')
  assert.equal(gameCountLabel({ loaded: true, total: 12, shown: 12, dueOnly: false }), '게임 12개')
  assert.equal(gameCountLabel({ loaded: true, total: 12, shown: 3, dueOnly: true }), '게임 3 / 12개')
})

test('only coming back from an open game to the list triggers a quiet refresh', () => {
  assert.equal(returnedToList('a', null), true)
  assert.equal(returnedToList(null, 'a'), false)
  assert.equal(returnedToList(null, null), false)
  assert.equal(returnedToList('a', 'b'), false)
  assert.equal(returnedToList('a', 'a'), false)
})

test('검색 중에는 전체 개수 대신 검색 결과 개수를 보인다', () => {
  assert.equal(gameCountLabel({ loaded: true, total: 12, shown: 3, dueOnly: false, searching: true }), '검색 결과 3개')
  assert.equal(gameCountLabel({ loaded: true, total: 0, shown: 0, dueOnly: false, searching: true }), '검색 결과 0개')
  assert.equal(gameCountLabel({ loaded: false, total: 0, shown: 0, dueOnly: false, searching: true }), '게임 불러오는 중…')
})
