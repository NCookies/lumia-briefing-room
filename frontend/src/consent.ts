import type { AppMode } from './appInfo'

export interface ConsentChoices {
  update: boolean
  labels: boolean
  logs: boolean
}

export const DEFAULT_CHOICES: ConsentChoices = { update: false, labels: false, logs: false }

export const LABEL_NOTE_MAX = 500

export const LABEL_TEXT = { pvp: '교전', pve: '그 외' } as const

export const isPending = (pending: string[], key: string): boolean => pending.includes(key)

export function consentPatch(choices: ConsentChoices, pending: string[]): Record<string, unknown> {
  const patch: Record<string, unknown> = {}
  if (isPending(pending, 'update')) patch.update = { check: choices.update }
  const telemetry: Record<string, boolean> = {}
  if (isPending(pending, 'labels')) telemetry.sendLabels = choices.labels
  if (isPending(pending, 'logs')) telemetry.sendLogs = choices.logs
  if (Object.keys(telemetry).length > 0) patch.telemetry = telemetry
  return patch
}

/** 라벨링 UI 는 개발 모드에서도 숨긴다(라벨링 재설계 전까지, 2026-10-02). 라벨 전송 동의는 이미 붙인 라벨의 전송에만 쓰인다. */
export function showLabelingUi(_mode: AppMode): boolean {
  return false
}

export const clampLabelNote = (text: string): string => text.slice(0, LABEL_NOTE_MAX)
