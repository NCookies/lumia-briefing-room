import assert from 'node:assert/strict'
import test from 'node:test'

import { reanalyzeConfirmMessage, reanalyzeStatusText } from '../src/reanalyze.ts'

test('원본 녹화가 있으면 풀영상·후보 전부, 없으면 후보만이라고 알린다', () => {
  const full = reanalyzeConfirmMessage('full')
  assert.match(full, /원본 스팀 녹화/)
  assert.match(full, /풀영상/)
  assert.match(full, /후보/)
  assert.match(full, /보관한 클립/)
  const only = reanalyzeConfirmMessage('candidates')
  assert.match(only, /이미 지워져/)
  assert.match(only, /풀영상은 그대로/)
  assert.doesNotMatch(only, /풀영상을 새로/)
})

test('다시 분석하면 사라지는 수정 사항을 미리 알린다', () => {
  for (const mode of ['full', 'candidates'] as const) assert.match(reanalyzeConfirmMessage(mode), /무시·이름·범위 수정은 초기화/)
})

test('진행 문구: 방식별 문구와 퍼센트, 끝남, 오류', () => {
  assert.equal(reanalyzeStatusText({ state: 'running', message: '', fraction: 0.42, mode: 'full' }), '풀영상과 후보를 다시 만드는 중… 42%')
  assert.equal(reanalyzeStatusText({ state: 'running', message: '', fraction: 0.1, mode: null }), '다시 분석하는 중… 10%')
  assert.equal(reanalyzeStatusText({ state: 'done', message: '', fraction: 1, mode: 'candidates' }), '후보를 다시 찾았습니다')
  assert.equal(reanalyzeStatusText({ state: 'done', message: '', fraction: 1, mode: 'full' }), '풀영상과 후보를 다시 만들었습니다')
  assert.equal(reanalyzeStatusText({ state: 'error', message: '원본 없음', fraction: 0, mode: null }), '원본 없음')
  assert.equal(reanalyzeStatusText({ state: 'idle', message: '', fraction: 0, mode: null }), null)
})
