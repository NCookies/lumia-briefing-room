import type { ActivityTask } from './activity'

export async function getActivity(): Promise<ActivityTask[]> {
  const res = await fetch('/api/activity')
  if (!res.ok) throw new Error(`작업 현황을 불러오지 못했습니다 (${res.status})`)
  return (await res.json()).tasks as ActivityTask[]
}
