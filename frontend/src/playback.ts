export type PlaybackMode = 'native' | 'proxy'

export const HEVC_TYPES = ['video/mp4; codecs="hvc1.1.6.L93.B0"', 'video/mp4; codecs="hev1.1.6.L93.B0"']
const MODE_KEY = 'lumia.playback'

export function initialMode(canPlay: string, remembered: PlaybackMode | null): PlaybackMode {
  if (remembered) return remembered
  return canPlay === '' ? 'proxy' : 'native'
}

export function needsProxy(state: { errored: boolean; videoWidth: number }): boolean {
  return state.errored || state.videoWidth === 0
}

export function proxyProgressText(progress: number): string {
  const percent = Math.round(Math.max(0, Math.min(1, progress)) * 100)
  return `재생용 영상을 만드는 중… ${percent}%`
}

export function prefetchTarget(ids: string[], index: number, mode: PlaybackMode, proxyReady: boolean): string | null {
  if (mode !== 'proxy' || !proxyReady || index < 0) return null
  return ids[index + 1] ?? null
}

// play() 는 일시정지·새 로드에 끊기거나(AbortError) 자동 재생 정책에 막혀도(NotAllowedError) 거부된다 - 영상을 못 읽은 게 아니다.
export function isPlaybackFailure(err: unknown): boolean {
  const name = (err as { name?: unknown } | null | undefined)?.name
  return name !== 'AbortError' && name !== 'NotAllowedError'
}

export const CODEC_STORE_URL = 'https://apps.microsoft.com/detail/9nmzlz57r3t7'

export function browserCanPlayHevc(): string {
  const probe = document.createElement('video')
  return HEVC_TYPES.map((t) => probe.canPlayType(t)).find((r) => r !== '') ?? ''
}

// 스팀 녹화는 Main10(hev1.2.4.L123.B0)이라, 판정이 Main 만 보면 "된다"고 해도 실제 영상은 안 나올 수 있다 - 둘을 따로 재 둔다.
const MAIN_TYPE = 'video/mp4; codecs="hvc1.1.6.L93.B0"'
const MAIN10_TYPE = 'video/mp4; codecs="hvc1.2.4.L123.B0"'

export interface DecodeCapability {
  supported: boolean
  smooth: boolean
  powerEfficient: boolean
}

export function describeBrowser(brands: { brand: string; version: string }[] | undefined, ua: string): string {
  const named = brands?.find((b) => !/not.?a.?brand|^chromium$/i.test(b.brand)) ?? brands?.find((b) => /^chromium$/i.test(b.brand))
  if (named) return `${named.brand} ${named.version}`.slice(0, 64)
  for (const [token, name] of [['Edg', 'Edge'], ['OPR', 'Opera'], ['Whale', 'Whale'], ['Firefox', 'Firefox'], ['Chrome', 'Chrome']]) {
    const version = new RegExp(`${token}/(\\d+)`).exec(ua)?.[1]
    if (version) return `${name} ${version}`
  }
  return 'unknown'
}

export function formatHevcProbe(main: string, main10: string, capability: DecodeCapability | null): string {
  let mc = 'n/a'
  if (capability) {
    mc = capability.supported
      ? ['supported', capability.smooth && 'smooth', capability.powerEfficient && 'efficient'].filter(Boolean).join(',')
      : 'unsupported'
  }
  return `main=${main || 'no'} main10=${main10 || 'no'} mc=${mc}`
}

export function fullVideoFailureDetail(state: { videoWidth: number; errorCode: number | null }, browser: string): string {
  return `videoWidth=${state.videoWidth} error=${state.errorCode ?? 'none'} browser=${browser}`
}

export function currentBrowserName(): string {
  const data = (navigator as { userAgentData?: { brands?: { brand: string; version: string }[] } }).userAgentData
  return describeBrowser(data?.brands, navigator.userAgent)
}

function webglRenderer(): string {
  try {
    const gl = document.createElement('canvas').getContext('webgl')
    const info = gl?.getExtension('WEBGL_debug_renderer_info')
    return info && gl ? String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL)).slice(0, 128) : ''
  } catch {
    return ''
  }
}

async function main10Capability(): Promise<DecodeCapability | null> {
  try {
    const info = await navigator.mediaCapabilities.decodingInfo({
      type: 'file',
      video: { contentType: MAIN10_TYPE, width: 2560, height: 1440, bitrate: 20_000_000, framerate: 60 },
    })
    return { supported: info.supported, smooth: info.smooth, powerEfficient: info.powerEfficient }
  } catch {
    return null
  }
}

export interface PlaybackProbe {
  hevcPlayable: boolean
  browser: string
  hevcProbe: string
  browserGpu: string
}

export async function probePlayback(): Promise<PlaybackProbe> {
  const video = document.createElement('video')
  return {
    hevcPlayable: browserCanPlayHevc() !== '',
    browser: currentBrowserName(),
    hevcProbe: formatHevcProbe(video.canPlayType(MAIN_TYPE), video.canPlayType(MAIN10_TYPE), await main10Capability()),
    browserGpu: webglRenderer(),
  }
}

export function rememberedMode(): PlaybackMode | null {
  try {
    const value = sessionStorage.getItem(MODE_KEY)
    return value === 'proxy' ? 'proxy' : null
  } catch {
    return null
  }
}

export function rememberProxyMode(): void {
  try {
    sessionStorage.setItem(MODE_KEY, 'proxy')
  } catch {
    // 저장하지 못해도 이번 클립은 프록시로 재생된다
  }
}
