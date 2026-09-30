import assert from 'node:assert/strict'
import test from 'node:test'

import { GUIDE_FOLDER_TREE, GUIDE_SECTIONS } from '../src/guide.ts'

const all = GUIDE_SECTIONS.flatMap((s) => [s.title, ...s.body]).join('\n')

test('가이드는 풀영상·교전 후보·클립·폴더 구조·입력 소스를 다룬다', () => {
  assert.deepEqual(GUIDE_SECTIONS.map((s) => s.title), ['풀영상', '교전 후보', '클립 — 보관과 저장', '폴더 구조', '스팀 녹화 / 영상 파일'])
})

test('보관과 저장을 구분해 쓴다 - 옛 문구를 쓰지 않는다', () => {
  assert.match(all, /보관/)
  assert.match(all, /다시 저장/)
  assert.doesNotMatch(all, /클립으로 저장|자동 저장|직접 저장|저장한 클립/)
})

test('폴더 그림은 새 영어 폴더 이름과 한글 카테고리 이름을 쓴다', () => {
  for (const name of ['clips', 'full_video', 'steam_replay', 'vod', '보관함', '자동 보관']) assert.ok(GUIDE_FOLDER_TREE.includes(name), name)
  assert.ok(!GUIDE_FOLDER_TREE.includes('풀영상 폴더'))
})
