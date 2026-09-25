import type { DiagnosticsPreview, DiagnosticsResult, TelemetryPreview, TelemetryStatus } from './telemetry'

const BASE = '/api'

async function jsonOrThrow<T>(res: Response, action: string): Promise<T> {
  if (!res.ok) {
    let detail = ''
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      // 본문이 JSON 이 아니면 상태 코드만 알린다
    }
    throw new Error(detail || `${action}에 실패했습니다 (${res.status})`)
  }
  return res.json()
}

export const getTelemetryStatus = async (): Promise<TelemetryStatus> =>
  jsonOrThrow(await fetch(`${BASE}/telemetry/status`), '전송 상태 불러오기')

export const getTelemetryPreview = async (): Promise<TelemetryPreview> =>
  jsonOrThrow(await fetch(`${BASE}/telemetry/preview`), '보낼 내용 불러오기')

export const deleteSentData = async (): Promise<{ ok: boolean; deleted: boolean }> =>
  jsonOrThrow(await fetch(`${BASE}/telemetry/delete`, { method: 'POST' }), '삭제 요청')

export const getDiagnosticsPreview = async (): Promise<DiagnosticsPreview> =>
  jsonOrThrow(await fetch(`${BASE}/telemetry/diagnostics/preview`), '진단 내용 불러오기')

export const sendDiagnostics = async (): Promise<DiagnosticsResult> =>
  jsonOrThrow(await fetch(`${BASE}/telemetry/diagnostics/send`, { method: 'POST' }), '진단 정보 보내기')

export const getPrivacyText = async (): Promise<string> =>
  (await jsonOrThrow<{ markdown: string }>(await fetch(`${BASE}/privacy`), '개인정보 처리 안내 불러오기')).markdown

export const reportClientCapabilities = async (capabilities: { hevcPlayable: boolean }): Promise<void> => {
  await jsonOrThrow(
    await fetch(`${BASE}/client-capabilities`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(capabilities),
    }),
    '브라우저 기능 알리기',
  )
}
