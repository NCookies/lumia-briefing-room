import assert from 'node:assert/strict'
import test from 'node:test'

import { GUIDE_CHIPS, GUIDE_FOLDER_TREE, GUIDE_TABS, SSD_ADVICE, parseGuideText, type GuideBlock } from '../src/guide.ts'

function textsOf(block: GuideBlock): string[] {
  switch (block.kind) {
    case 'steps':
      return block.items
    case 'notes':
      return [block.title, ...block.items]
    case 'paras':
      return [...(block.title ? [block.title] : []), ...block.lines]
    case 'callout':
      return [block.title, ...block.lines]
    default:
      return []
  }
}

const allTexts = GUIDE_TABS.flatMap((t) => [t.label, ...t.blocks.flatMap(textsOf)])
const all = allTexts.join('\n')

test('가이드 탭은 시작하기 | 풀영상 화면 | 클립 | 폴더 | 단축키 순서다', () => {
  assert.deepEqual(GUIDE_TABS.map((t) => t.label), ['시작하기', '풀영상 화면', '클립', '폴더', '단축키'])
  assert.equal(new Set(GUIDE_TABS.map((t) => t.id)).size, GUIDE_TABS.length)
})

test('시작하기는 4단계 흐름과 알아 두면 좋은 것 3줄이다', () => {
  const start = GUIDE_TABS[0].blocks
  const steps = start.find((b) => b.kind === 'steps')
  assert.ok(steps && steps.kind === 'steps')
  assert.equal(steps.items.length, 4)
  const notes = start.find((b) => b.kind === 'notes')
  assert.ok(notes && notes.kind === 'notes')
  assert.equal(notes.items.length, 3)
})

test('단축키 탭은 표 블록 하나이고 폴더 탭은 그림 블록을 가진다', () => {
  assert.deepEqual(GUIDE_TABS[4].blocks.map((b) => b.kind), ['shortcuts'])
  assert.ok(GUIDE_TABS[3].blocks.some((b) => b.kind === 'tree'))
})

test('백틱은 용어 칩, 중괄호는 키로 쪼갠다', () => {
  assert.deepEqual(parseGuideText('먼저 `보관`을 누르고 {Ctrl+S} 도 됩니다'), [
    { type: 'text', value: '먼저 ' },
    { type: 'chip', value: '보관' },
    { type: 'text', value: '을 누르고 ' },
    { type: 'kbd', value: 'Ctrl+S' },
    { type: 'text', value: ' 도 됩니다' },
  ])
  assert.deepEqual(parseGuideText('그냥 글'), [{ type: 'text', value: '그냥 글' }])
})

test('쪼갠 뒤에는 백틱·중괄호가 글자로 남지 않고 칩은 모두 등록된 용어다', () => {
  for (const s of allTexts) {
    for (const seg of parseGuideText(s)) {
      if (seg.type === 'text') assert.doesNotMatch(seg.value, /[`{}]/, s)
      if (seg.type === 'chip') assert.ok(seg.value in GUIDE_CHIPS, `미등록 칩: ${seg.value}`)
    }
  }
})

test('칩 용어는 실제 화면 버튼 이름이다', () => {
  for (const name of ['보관', '보관됨', '다시 저장', '삭제', '클립 삭제', '구간 삭제', '메모', '고정', '자동 보관', '보관함']) {
    assert.ok(name in GUIDE_CHIPS, name)
  }
})

test('보관과 저장을 구분해 쓴다 - 옛 문구를 쓰지 않는다', () => {
  assert.match(all, /보관/)
  assert.match(all, /다시 저장/)
  assert.doesNotMatch(all, /클립으로 저장|자동 저장|직접 저장|저장한 클립|보관 해제|무시/)
})

test('옵션 탭 이름은 실제 이름을 쓴다 - 옛 이름 "다시보기" 가 없다', () => {
  assert.doesNotMatch(all, /다시보기에서|옵션 → 다시보기/)
  assert.match(all, /옵션 → 영상 파일/)
})

test('SSD 권장 문구는 녹화 폴더 SSD·클립 풀영상은 다른 디스크를 말한다', () => {
  assert.match(SSD_ADVICE, /SSD/)
  assert.match(SSD_ADVICE, /다른 디스크/)
  assert.match(all, /SSD/)
})

test('폴더 그림은 새 영어 폴더 이름과 한글 카테고리 이름을 쓴다', () => {
  for (const name of ['clips', 'full_video', 'steam_replay', 'vod', '보관함', '자동 보관']) assert.ok(GUIDE_FOLDER_TREE.includes(name), name)
  assert.ok(!GUIDE_FOLDER_TREE.includes('풀영상 폴더'))
})

test('한 단락은 두 문장을 넘기지 않는다', () => {
  for (const s of allTexts) {
    const sentences = s.split(/\.\s+/).filter(Boolean)
    assert.ok(sentences.length <= 2, `너무 김: ${s}`)
  }
})
