export interface AppNotice {
  kind: string
  title: string
  message: string
  at: string
}

export async function getNotices(): Promise<AppNotice[]> {
  const res = await fetch('/api/notices')
  if (!res.ok) throw new Error(`알림을 불러오지 못했습니다 (${res.status})`)
  return (await res.json()).notices as AppNotice[]
}

export async function dismissNotice(kind: string): Promise<void> {
  const res = await fetch(`/api/notices/${encodeURIComponent(kind)}/dismiss`, { method: 'POST' })
  if (!res.ok && res.status !== 404) throw new Error(`알림을 닫지 못했습니다 (${res.status})`)
}
