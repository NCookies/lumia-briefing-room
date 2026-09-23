import assert from 'node:assert/strict'
import test from 'node:test'

import { initialMode, needsProxy, proxyProgressText } from '../src/playback.ts'

test('starts native unless the browser cannot play HEVC or a failure was remembered', () => {
  assert.equal(initialMode('probably', null), 'native')
  assert.equal(initialMode('maybe', null), 'native')
  assert.equal(initialMode('', null), 'proxy')
  assert.equal(initialMode('probably', 'proxy'), 'proxy')
})

test('a video with zero width or an error needs the proxy even if canPlayType said probably', () => {
  assert.equal(needsProxy({ errored: false, videoWidth: 2560 }), false)
  assert.equal(needsProxy({ errored: false, videoWidth: 0 }), true)
  assert.equal(needsProxy({ errored: true, videoWidth: 2560 }), true)
})

test('progress text rounds to whole percent and clamps', () => {
  assert.equal(proxyProgressText(0.426), '재생용 영상을 만드는 중… 43%')
  assert.equal(proxyProgressText(2), '재생용 영상을 만드는 중… 100%')
  assert.equal(proxyProgressText(-1), '재생용 영상을 만드는 중… 0%')
})
