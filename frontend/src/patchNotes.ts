export interface PatchNoteSection {
  title: string
  items: string[]
}

export interface PatchNoteRelease {
  version: string
  date: string
  sections: PatchNoteSection[]
}

export function formatReleaseDate(date: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date)
  if (!match) return ''
  return `${Number(match[1])}년 ${Number(match[2])}월 ${Number(match[3])}일`
}

export function isCurrentRelease(release: { version: string }, currentVersion: string): boolean {
  return currentVersion !== '' && release.version === currentVersion
}
