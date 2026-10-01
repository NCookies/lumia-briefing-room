import assert from 'node:assert/strict'
import test from 'node:test'

import { vodAnalyzeConfirmMessage } from '../src/vodAnalyzeConfirm.ts'

test('다시 분석·다시 만들기는 자동 저장이면 보관 카테고리로 옮긴 클립까지 지워진다고 알린다', () => {
  for (const options of [{ force: true }, { rebuild: true }]) {
    const message = vodAnalyzeConfirmMessage('방송.mp4', options)
    assert.match(message, /방송\.mp4/)
    assert.match(message, /보관 카테고리로 옮긴 것까지 모두 지우고 새로 만듭니다/)
    assert.match(message, /수동 저장이면 저장한 클립은 그대로/)
  }
})

test('처음 분석은 지울 클립이 없으니 경고하지 않고 줄 서기만 알린다', () => {
  const message = vodAnalyzeConfirmMessage('방송.mp4', {})
  assert.doesNotMatch(message, /지우고 새로/)
  assert.match(message, /줄을 서서 차례로/)
})
