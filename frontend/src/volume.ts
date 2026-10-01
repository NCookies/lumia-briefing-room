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

export const VOLUME_STEP = 0.05

/** 화살표로 볼륨을 5% 씩 바꾼다. 음소거 중 올리면 음소거를 푼다. */
export function stepVolume(state: VolumeState, direction: 1 | -1): VolumeState {
  const volume = Math.min(1, Math.max(0, Math.round((state.volume + direction * VOLUME_STEP) * 100) / 100))
  return { volume, muted: direction === 1 ? false : state.muted }
}
