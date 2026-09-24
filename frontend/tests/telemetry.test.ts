import assert from 'node:assert/strict'
import test from 'node:test'

import {
  formatSentAt,
  parseInlineBold,
  parsePrivacy,
  pendingText,
  sendStateText,
  type TelemetryStatus,
} from '../src/telemetry.ts'

const base: TelemetryStatus = {
  installId: '3f2b8c1e-5a4d-4e6f-9b7a-1c2d3e4f5a6b',
  displayId: 'LUMIA-7K3F-9QX2',
  sendLabels: true,
  sendLogs: false,
  endpointConfigured: true,
  mode: 'release',
  canSendInThisMode: true,
  pendingLabels: 0,
  pendingLogs: 0,
  lastLabelsSentAt: null,
  lastLogsSentAt: null,
}

test('state text says nothing is sent when both toggles are off', () => {
  assert.match(sendStateText({ ...base, sendLabels: false, sendLogs: false }), /꺼져 있습니다/)
})

test('state text explains a build without server info and dev mode', () => {
  assert.match(sendStateText({ ...base, endpointConfigured: false }), /서버 연결 정보가 없어/)
  assert.match(sendStateText({ ...base, canSendInThisMode: false, mode: 'dev' }), /개발 모드/)
})

test('state text says once a day when sending is on', () => {
  assert.match(sendStateText(base), /하루에 한 번/)
})

test('off wins over missing endpoint so the user is never told a disabled feature is broken', () => {
  assert.match(sendStateText({ ...base, sendLabels: false, endpointConfigured: false }), /꺼져 있습니다/)
})

test('sent-at is a friendly local time or "not yet"', () => {
  assert.equal(formatSentAt(null), '아직 보낸 적 없음')
  const local = new Date(2026, 8, 25, 9, 5)
  assert.equal(formatSentAt(local.getTime() / 1000), '2026-09-25 09:05')
})

test('pending text', () => {
  assert.equal(pendingText(0, '라벨'), '보낼 라벨 없음')
  assert.equal(pendingText(3, '오류 로그'), '보낼 오류 로그 3건')
})

test('privacy markdown becomes typed blocks', () => {
  const md = [
    '# 개인정보 처리 안내',
    '',
    '> 초안입니다.',
    '',
    '## 1. 기본 원칙',
    '',
    '- 첫째 **굵게**',
    '- 둘째',
    '',
    '문단 한 줄',
    '이어지는 줄',
    '',
    '| 종류 | 내용 |',
    '|---|---|',
    '| 라벨 | 교전 / 그 외 |',
    '| 로그 | 오류 |',
  ].join('\n')
  const blocks = parsePrivacy(md)
  assert.deepEqual(blocks[0], { type: 'h1', text: '개인정보 처리 안내' })
  assert.deepEqual(blocks[1], { type: 'note', text: '초안입니다.' })
  assert.deepEqual(blocks[2], { type: 'h2', text: '1. 기본 원칙' })
  assert.deepEqual(blocks[3], { type: 'list', items: ['첫째 **굵게**', '둘째'] })
  assert.deepEqual(blocks[4], { type: 'p', text: '문단 한 줄 이어지는 줄' })
  assert.deepEqual(blocks[5], {
    type: 'table',
    header: ['종류', '내용'],
    rows: [
      ['라벨', '교전 / 그 외'],
      ['로그', '오류'],
    ],
  })
})

test('inline bold splits into plain and strong parts', () => {
  assert.deepEqual(parseInlineBold('가 **나** 다'), [
    { text: '가 ', bold: false },
    { text: '나', bold: true },
    { text: ' 다', bold: false },
  ])
  assert.deepEqual(parseInlineBold('굵게 없음'), [{ text: '굵게 없음', bold: false }])
})

test('the real privacy document parses without leaving markdown markers behind', async () => {
  const { readFileSync } = await import('node:fs')
  const md = readFileSync(new URL('../../docs/privacy.md', import.meta.url), 'utf-8')
  const blocks = parsePrivacy(md)
  assert.ok(blocks.length > 5)
  assert.ok(blocks.some((b) => b.type === 'table'))
  const flat = JSON.stringify(blocks)
  assert.ok(!flat.includes('"text":"#'))
})
