import type { PatchNoteRelease } from './patchNotes'

export async function getPatchNotes(): Promise<PatchNoteRelease[]> {
  const res = await fetch('/api/changelog')
  if (!res.ok) throw new Error('패치노트를 불러오지 못했습니다')
  return (await res.json()).releases as PatchNoteRelease[]
}
