import type { ConsentChoices } from './consent'

const BASE = '/api'

interface ConsentConfig {
  update?: { check?: boolean }
  telemetry?: { sendLabels?: boolean; sendLogs?: boolean }
}

export async function getConsentChoices(): Promise<ConsentChoices> {
  const res = await fetch(`${BASE}/config`)
  if (!res.ok) throw new Error(`설정 불러오기에 실패했습니다 (${res.status})`)
  const cfg: ConsentConfig = await res.json()
  return {
    update: cfg.update?.check === true,
    labels: cfg.telemetry?.sendLabels === true,
    logs: cfg.telemetry?.sendLogs === true,
  }
}

export async function saveConsentPatch(patch: Record<string, unknown>): Promise<void> {
  if (Object.keys(patch).length === 0) return
  const res = await fetch(`${BASE}/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
  if (!res.ok) throw new Error(`설정 저장에 실패했습니다 (${res.status})`)
}
