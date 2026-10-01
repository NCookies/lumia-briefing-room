export type ConfirmFocus = 'cancel' | 'confirm' | 'other'

export type ConfirmKeyResult =
  | { kind: 'pass' }
  | { kind: 'swallow' }
  | { kind: 'native' }
  | { kind: 'cancel' }
  | { kind: 'confirm' }
  | { kind: 'focus'; to: 'cancel' | 'confirm' }

/** 확인 창의 키 처리. 창이 떠 있는 동안 뒤 화면의 단축키는 모두 막고(`swallow`), 버튼 사이를 ←/→ 로 옮기며 Space·Enter 로 누른다. */
export function confirmKeyAction(key: string, focus: ConfirmFocus, repeat = false): ConfirmKeyResult {
  if (key === 'Tab') return { kind: 'pass' }
  if (key === 'Escape') return { kind: 'cancel' }
  if (key === 'ArrowLeft') return { kind: 'focus', to: 'cancel' }
  if (key === 'ArrowRight') return { kind: 'focus', to: 'confirm' }
  if (key === 'Enter' || key === ' ') {
    if (repeat) return { kind: 'swallow' }
    if (focus === 'cancel') return { kind: 'cancel' }
    if (focus === 'confirm') return { kind: 'confirm' }
    return key === 'Enter' ? { kind: 'confirm' } : { kind: 'native' }
  }
  return { kind: 'swallow' }
}
