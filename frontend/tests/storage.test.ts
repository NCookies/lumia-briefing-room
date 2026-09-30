import assert from 'node:assert/strict'
import { test } from 'node:test'
import { folderName, joinPath, parentPath, recordingDiskWarning, samePath, suggestedRootFromLegacy, structureLines } from '../src/storage.ts'

test('parentPath handles windows and forward slashes and trailing separators', () => {
  assert.equal(parentPath('H:\\lumia_briefingroom_vod\\clips'), 'H:\\lumia_briefingroom_vod')
  assert.equal(parentPath('H:\\lumia_briefingroom_vod\\clips\\'), 'H:\\lumia_briefingroom_vod')
  assert.equal(parentPath('/a/b/c'), '/a/b')
  assert.equal(parentPath('H:\\clips'), 'H:\\')
  assert.equal(parentPath('H:\\'), '')
})

test('suggestedRootFromLegacy uses the folder that holds the old clips folder', () => {
  assert.equal(suggestedRootFromLegacy('H:\\lumia_briefingroom_vod\\clips'), 'H:\\lumia_briefingroom_vod')
  assert.equal(
    suggestedRootFromLegacy('C:\\Users\\me\\Videos\\LumiaBriefingRoom\\clips'),
    'C:\\Users\\me\\Videos\\LumiaBriefingRoom',
  )
  assert.equal(suggestedRootFromLegacy(''), '')
})

test('samePath ignores case, separators and trailing slash', () => {
  assert.equal(samePath('H:\\Store\\', 'h:/store'), true)
  assert.equal(samePath('H:\\Store', 'H:\\Store2'), false)
  assert.equal(samePath('', ''), false)
})

test('joinPath uses the separator style of the base', () => {
  assert.equal(joinPath('H:\\store', '클립'), 'H:\\store\\클립')
  assert.equal(joinPath('/a/b', '클립'), '/a/b/클립')
  assert.equal(joinPath('H:\\store\\', '풀영상'), 'H:\\store\\풀영상')
})

test('folderName is the last path component', () => {
  assert.equal(folderName('H:\\a\\b\\'), 'b')
})

test('structureLines describes the folders and marks the full video override', () => {
  const plain = structureLines('H:\\store', null)
  assert.ok(plain.some((l) => l.path === 'H:\\store\\clips' && l.note.includes('자동으로 지워지지 않')))
  assert.ok(plain.some((l) => l.path === 'H:\\store\\full_video' && l.note.includes('자동으로 지워')))
  const moved = structureLines('H:\\store', 'D:\\big')
  assert.ok(moved.some((l) => l.path === 'D:\\big' && l.note.includes('자동으로 지워')))
  assert.ok(!moved.some((l) => l.path === 'H:\\store\\full_video'))
})

test('recordingDiskWarning names the folders that share the steam recording disk', () => {
  assert.equal(recordingDiskWarning(undefined), null)
  assert.equal(recordingDiskWarning({ clips: false, fullVideos: false }), null)
  const full = recordingDiskWarning({ clips: false, fullVideos: true })
  assert.ok(full?.startsWith('풀영상 폴더가 스팀 녹화와 같은 디스크'))
  assert.ok(full?.includes('다른 디스크'))
  assert.ok(recordingDiskWarning({ clips: true, fullVideos: true })?.startsWith('풀영상·클립 폴더가'))
  assert.ok(recordingDiskWarning({ clips: true, fullVideos: false })?.startsWith('클립 폴더가'))
})
