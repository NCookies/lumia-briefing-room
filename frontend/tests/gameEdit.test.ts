import assert from 'node:assert/strict'
import test from 'node:test'

import { draftOf, gameHeading, parseDraft, TITLE_MAX, titleValue } from '../src/gameEdit.ts'

test('초안: 읽은 결과를 입력 칸 문자열로 옮긴다(없는 값은 빈 칸)', () => {
  assert.deepEqual(draftOf({ placement: 3, matchType: 'rank', tk: 12, kills: 4, assists: 0 }), {
    placement: '3', matchType: 'rank', outcome: '', tk: '12', kills: '4', assists: '0',
  })
  assert.deepEqual(draftOf(null), { placement: '', matchType: 'unknown', outcome: '', tk: '', kills: '', assists: '' })
})

test('일반 게임: 순위·일반/랭크·TK/K/A 를 숫자로 바꿔 보낸다', () => {
  const r = parseDraft({ placement: '3', matchType: 'rank', outcome: '', tk: '12', kills: '4', assists: '0' }, false)
  assert.deepEqual(r, { ok: true, patch: { placement: 3, matchType: 'rank', tk: 12, kills: 4, assists: 0 } })
})

test('빈 칸은 null 로 보내 값을 비운다', () => {
  const r = parseDraft({ placement: '', matchType: 'unknown', outcome: '', tk: '', kills: '', assists: '' }, false)
  assert.deepEqual(r, { ok: true, patch: { placement: null, matchType: 'unknown', tk: null, kills: null, assists: null } })
})

test('코발트: 순위 대신 승리/패배를 보내고 순위·일반/랭크는 보내지 않는다', () => {
  const r = parseDraft({ placement: '', matchType: 'unknown', outcome: '승리', tk: '', kills: '5', assists: '' }, true)
  assert.deepEqual(r, { ok: true, patch: { outcome: '승리', tk: null, kills: 5, assists: null } })
})

test('잘못된 입력은 어느 칸이 문제인지 알려 준다', () => {
  assert.deepEqual(parseDraft({ ...draftOf(null), placement: '0' }, false), { ok: false, error: '순위는 1~99 사이의 정수로 입력하세요' })
  assert.deepEqual(parseDraft({ ...draftOf(null), placement: '1.5' }, false), { ok: false, error: '순위는 1~99 사이의 정수로 입력하세요' })
  assert.deepEqual(parseDraft({ ...draftOf(null), kills: '-1' }, false), { ok: false, error: 'K 는 0 이상의 정수로 입력하세요' })
  assert.deepEqual(parseDraft({ ...draftOf(null), tk: 'a' }, false), { ok: false, error: 'TK 는 0 이상의 정수로 입력하세요' })
  assert.deepEqual(parseDraft({ ...draftOf(null), assists: '1000' }, false), { ok: false, error: 'A 는 0 이상의 정수로 입력하세요' })
})

test('제목: 앞뒤 공백을 지우고 빈 값은 null(제목 없음)', () => {
  assert.equal(titleValue('  첫 우승 '), '첫 우승')
  assert.equal(titleValue('   '), null)
  assert.equal(titleValue('가'.repeat(TITLE_MAX + 5))?.length, TITLE_MAX)
})

test('화면 머리줄: 사용자 제목 > 영상 게임 제목(스트리머 · 게임 N) > 경기 키', () => {
  assert.equal(gameHeading({ gameKey: 'k', title: '내 제목', source: 'vod', streamer: 's', vodGameIndex: 2 }), '내 제목')
  assert.equal(gameHeading({ gameKey: 'k', title: null, source: 'vod', streamer: 's', vodGameIndex: 2 }), 's · 게임 2')
  assert.equal(gameHeading({ gameKey: 'k', title: null, source: 'steam' }), 'k')
})
