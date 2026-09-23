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

export function browserCanPlayHevc(): string {
  const probe = document.createElement('video')
  return HEVC_TYPES.map((t) => probe.canPlayType(t)).find((r) => r !== '') ?? ''
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
