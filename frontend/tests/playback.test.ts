import assert from 'node:assert/strict'
import test from 'node:test'

import { initialMode, needsProxy, prefetchTarget, proxyProgressText } from '../src/playback.ts'

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

const IDS = ['a', 'b', 'c']

test('prefetches the next clip only while playing through the proxy and the current proxy is ready', () => {
  assert.equal(prefetchTarget(IDS, 0, 'proxy', true), 'b')
  assert.equal(prefetchTarget(IDS, 1, 'proxy', true), 'c')
})

test('does not prefetch before the current proxy is ready, in native mode, or at the last clip', () => {
  assert.equal(prefetchTarget(IDS, 0, 'proxy', false), null)
  assert.equal(prefetchTarget(IDS, 0, 'native', true), null)
  assert.equal(prefetchTarget(IDS, 2, 'proxy', true), null)
  assert.equal(prefetchTarget([], 0, 'proxy', true), null)
  assert.equal(prefetchTarget(IDS, -1, 'proxy', true), null)
})
