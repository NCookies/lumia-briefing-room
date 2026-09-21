const KEY = 'lumia.player.volume'

export interface VolumeState {
  volume: number
  muted: boolean
}

export function loadVolume(): VolumeState {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) {
      const v = JSON.parse(raw) as Partial<VolumeState>
      if (typeof v.volume === 'number' && v.volume >= 0 && v.volume <= 1) {
        return { volume: v.volume, muted: v.muted === true }
      }
    }
  } catch {
    // localStorage 를 못 쓰는 환경에서는 기본값으로 동작한다
  }
  return { volume: 1, muted: false }
}

export function saveVolume(state: VolumeState): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(state))
  } catch {
    // 저장 실패는 무시한다
  }
}
