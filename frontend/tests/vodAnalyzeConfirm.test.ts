import assert from 'node:assert/strict'
import test from 'node:test'

import { vodAnalyzeConfirmMessage } from '../src/vodAnalyzeConfirm.ts'

test('다시 분석 확인 창은 내부 동작 설명 없이 짧게 묻는다', () => {
  for (const options of [{ force: true }, { rebuild: true }]) {
    const message = vodAnalyzeConfirmMessage('방송.mp4', options)
    assert.match(message, /방송\.mp4/)
    assert.doesNotMatch(message, /클립|카테고리|줄을 서서/)
    assert.equal(message.split(String.fromCharCode(10)).length, 2)
  }
})

test('처음 분석은 풀영상이 디스크를 쓴다는 것만 알린다', () => {
  const message = vodAnalyzeConfirmMessage('방송.mp4', {})
  assert.match(message, /디스크/)
  assert.doesNotMatch(message, /카테고리|줄을 서서/)
})
