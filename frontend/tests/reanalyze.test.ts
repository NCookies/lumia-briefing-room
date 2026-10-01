import assert from 'node:assert/strict'
import test from 'node:test'

import { queueLabel, reanalyzeConfirmMessage, reanalyzeStatusText } from '../src/reanalyze.ts'

test('다시 분석 확인 창은 내부 동작 설명 없이 짧게 묻는다', () => {
  const message = reanalyzeConfirmMessage()
  assert.equal(message, ['이 게임을 다시 분석합니다.', '몇 분 정도 소요될 수 있습니다. 계속하시겠습니까?'].join(String.fromCharCode(10)))
})

test('진행 문구: 방식별 문구와 퍼센트, 끝남, 오류', () => {
  assert.equal(reanalyzeStatusText({ state: 'running', message: '', fraction: 0.42, mode: 'full' }), '풀영상과 후보를 다시 만드는 중… 42%')
  assert.equal(reanalyzeStatusText({ state: 'running', message: '', fraction: 0.1, mode: null }), '저장된 풀영상에서 클립을 다시 추출하는 중… 10%')
  assert.equal(reanalyzeStatusText({ state: 'done', message: '', fraction: 1, mode: 'candidates' }), '원본 녹화가 없어 저장된 풀영상에서 클립만 다시 추출했습니다')
  assert.equal(reanalyzeStatusText({ state: 'done', message: '', fraction: 1, mode: 'full' }), '풀영상과 후보를 다시 만들었습니다')
  assert.equal(reanalyzeStatusText({ state: 'error', message: '원본 없음', fraction: 0, mode: null }), '원본 없음')
  assert.equal(reanalyzeStatusText({ state: 'idle', message: '', fraction: 0, mode: null }), null)
})

test('대기 중 문구는 몇 번째인지 보이고 번호가 없으면 번호 없이 보인다', () => {
  assert.equal(queueLabel(1), '대기 중 (1번째)')
  assert.equal(queueLabel(3), '대기 중 (3번째)')
  assert.equal(queueLabel(null), '대기 중')
  assert.equal(queueLabel(undefined), '대기 중')
  assert.equal(reanalyzeStatusText({ state: 'queued', message: '', fraction: 0, mode: 'full', position: 2 }), '대기 중 (2번째)')
})

test('클립을 일부 못 뽑았으면 그 수를 알린다', () => {
  assert.equal(
    reanalyzeStatusText({ state: 'done', message: '', fraction: 1, mode: 'full', clipsMade: 3, clipsFailed: 2 }),
    '풀영상과 후보를 다시 만들었습니다 (클립 2개는 만들지 못했습니다)',
  )
})
