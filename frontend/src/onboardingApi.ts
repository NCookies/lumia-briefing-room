import type { FirstRunInfo } from './onboarding'

const BASE = '/api'

async function jsonOrThrow<T>(res: Response, action: string): Promise<T> {
  if (!res.ok) throw new Error(`${action}에 실패했습니다 (${res.status})`)
  return res.json()
}

export async function getFirstRun(): Promise<FirstRunInfo> {
  return jsonOrThrow(await fetch(`${BASE}/first-run`), '첫 실행 정보 조회')
}

export async function completeFirstRun(): Promise<void> {
  await jsonOrThrow(await fetch(`${BASE}/first-run/complete`, { method: 'POST' }), '설정 저장')
}

async function putConfig(body: unknown, action: string): Promise<void> {
  await jsonOrThrow(
    await fetch(`${BASE}/config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
    action,
  )
}

export const setRecordingRoot = (path: string) =>
  putConfig({ paths: { steamRecording: path } }, '녹화 폴더 저장')

export const setClipsDir = (path: string) => putConfig({ paths: { clips: path } }, '클립 폴더 저장')

export const DIAGNOSTICS_URL = `${BASE}/diagnostics`
