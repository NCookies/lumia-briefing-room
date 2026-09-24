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

export function showLabelingUi(mode: AppMode, sendLabels: boolean): boolean {
  return mode === 'dev' || sendLabels
}

export const clampLabelNote = (text: string): string => text.slice(0, LABEL_NOTE_MAX)
