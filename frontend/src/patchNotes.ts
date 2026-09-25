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

export function parseReleaseNotes(markdown: string): PatchNoteSection[] {
  const sections: PatchNoteSection[] = []
  let current: PatchNoteSection | null = null
  for (const raw of markdown.split(/\r?\n/)) {
    const line = raw.trim()
    if (/^-{3,}$/.test(line)) break
    const heading = /^#{2,4}\s+(.+)$/.exec(line)
    if (heading) {
      current = { title: heading[1].trim(), items: [] }
      sections.push(current)
      continue
    }
    const item = /^[-*]\s+(.+)$/.exec(line)
    if (item) {
      if (!current) {
        current = { title: '', items: [] }
        sections.push(current)
      }
      current.items.push(item[1].trim())
    }
  }
  return sections.filter((s) => s.items.length > 0)
}
