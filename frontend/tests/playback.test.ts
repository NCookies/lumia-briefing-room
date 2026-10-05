import assert from 'node:assert/strict'
import test from 'node:test'

import {
  describeBrowser,
  fullVideoFailureDetail,
  formatHevcProbe,
  initialMode,
  needsProxy,
  prefetchTarget,
  proxyProgressText,
} from '../src/playback.ts'

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

test('an interrupted or blocked play() is not a playback failure, anything else is', async () => {
  const { isPlaybackFailure } = await import('../src/playback.ts')
  assert.equal(isPlaybackFailure({ name: 'AbortError' }), false)
  assert.equal(isPlaybackFailure({ name: 'NotAllowedError' }), false)
  assert.equal(isPlaybackFailure({ name: 'NotSupportedError' }), true)
  assert.equal(isPlaybackFailure(new Error('boom')), true)
  assert.equal(isPlaybackFailure(undefined), true)
})

test('names the browser by its own brand, not by Chromium or the GREASE brand', () => {
  const brands = [
    { brand: 'Not.A/Brand', version: '99' },
    { brand: 'Chromium', version: '141' },
    { brand: 'NAVER Whale', version: '4' },
  ]
  assert.equal(describeBrowser(brands, ''), 'NAVER Whale 4')
  assert.equal(describeBrowser([{ brand: 'Chromium', version: '141' }], ''), 'Chromium 141')
  assert.equal(describeBrowser(undefined, 'Mozilla/5.0 (Windows NT 10.0; rv:130.0) Gecko/20100101 Firefox/130.0'), 'Firefox 130')
  assert.equal(describeBrowser(undefined, 'Mozilla/5.0 AppleWebKit/537.36 Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0'), 'Edge 141')
  assert.equal(describeBrowser(undefined, 'weird'), 'unknown')
})

test('summarises the HEVC probe so Main and Main10 and hardware support can be told apart', () => {
  const ok = { supported: true, smooth: true, powerEfficient: true }
  assert.equal(formatHevcProbe('probably', 'maybe', ok), 'main=probably main10=maybe mc=supported,smooth,efficient')
  assert.equal(formatHevcProbe('', '', { supported: false, smooth: false, powerEfficient: false }), 'main=no main10=no mc=unsupported')
  assert.equal(formatHevcProbe('probably', '', { supported: true, smooth: false, powerEfficient: false }), 'main=probably main10=no mc=supported')
  assert.equal(formatHevcProbe('', '', null), 'main=no main10=no mc=n/a')
})

test('describes a full-video failure including the silent black screen', () => {
  assert.equal(fullVideoFailureDetail({ videoWidth: 0, errorCode: null }, 'Chrome 141'), 'videoWidth=0 error=none browser=Chrome 141')
  assert.equal(fullVideoFailureDetail({ videoWidth: 0, errorCode: 4 }, 'Edge 141'), 'videoWidth=0 error=4 browser=Edge 141')
})
