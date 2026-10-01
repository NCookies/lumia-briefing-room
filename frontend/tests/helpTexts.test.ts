import assert from 'node:assert/strict'
import test from 'node:test'

import { AUTO_CLEAN_HELP, FULL_VIDEO_LOCATION_HELP, FULL_VIDEO_MISSING_HELP, RECORDING_STOPPED_HELP, SAVE_MODE_HELP, VOD_DELETE_SOURCE_HELP, VOD_TAB_HELP } from '../src/helpTexts.ts'
import { SSD_ADVICE } from '../src/guide.ts'
import { recordingDiskWarning } from '../src/storage.ts'

const ALL = { VOD_TAB_HELP, VOD_DELETE_SOURCE_HELP, AUTO_CLEAN_HELP, SAVE_MODE_HELP, FULL_VIDEO_LOCATION_HELP, FULL_VIDEO_MISSING_HELP, RECORDING_STOPPED_HELP }

test('도움말은 비어 있지 않고 백틱 같은 마크업 글자가 없다(HelpTip 은 글자 그대로 보여 준다)', () => {
  for (const [name, text] of Object.entries(ALL)) {
    assert.ok(text.length > 20, name)
    assert.doesNotMatch(text, /[`{}]/, name)
  }
})

test('자동 정리 도움말은 풀영상만 지우고 클립은 남는다고 말한다', () => {
  assert.match(AUTO_CLEAN_HELP, /풀영상/)
  assert.match(AUTO_CLEAN_HELP, /보관한 클립/)
})

test('클립 보관 방식 도움말은 직접·자동 보관을 구분하고 옛 용어를 쓰지 않는다', () => {
  assert.match(SAVE_MODE_HELP, /직접 보관/)
  assert.match(SAVE_MODE_HELP, /자동 보관/)
  assert.doesNotMatch(SAVE_MODE_HELP, /클립으로 저장|자동 저장|직접 저장/)
})

test('풀영상 위치·녹화 오류 도움말과 같은 디스크 경고는 SSD 권장을 담는다', () => {
  assert.ok(FULL_VIDEO_LOCATION_HELP.includes(SSD_ADVICE))
  assert.ok(RECORDING_STOPPED_HELP.includes(SSD_ADVICE))
  assert.match(recordingDiskWarning({ clips: false, fullVideos: true }) ?? '', /SSD/)
})

test('영상 파일 도움말은 옵션 → 영상 파일에서 추가하고 원본은 읽기만 한다고 말한다', () => {
  assert.match(VOD_TAB_HELP, /옵션 → 영상 파일/)
  assert.match(VOD_TAB_HELP, /읽기만/)
  assert.match(VOD_DELETE_SOURCE_HELP, /풀영상/)
  assert.match(VOD_DELETE_SOURCE_HELP, /휴지통/)
})
