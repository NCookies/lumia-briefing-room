export interface StructureLine {
  path: string
  note: string
}

const TRAILING = /[\\/]+$/

const trimEnd = (p: string) => p.replace(TRAILING, '')

export function parentPath(path: string): string {
  const trimmed = trimEnd(path)
  const cut = Math.max(trimmed.lastIndexOf('\\'), trimmed.lastIndexOf('/'))
  if (cut < 0) return ''
  const parent = trimmed.slice(0, cut)
  return /^[A-Za-z]:$/.test(parent) ? `${parent}\\` : parent
}

export function folderName(path: string): string {
  const trimmed = trimEnd(path)
  return trimmed.slice(Math.max(trimmed.lastIndexOf('\\'), trimmed.lastIndexOf('/')) + 1)
}

export function suggestedRootFromLegacy(legacyClips: string): string {
  return legacyClips ? parentPath(legacyClips) : ''
}

const normalize = (p: string) => trimEnd(p).replace(/\//g, '\\').toLowerCase()

export function samePath(a: string, b: string): boolean {
  return a !== '' && b !== '' && normalize(a) === normalize(b)
}

export function joinPath(base: string, name: string): string {
  const sep = base.includes('/') && !base.includes('\\') ? '/' : '\\'
  return `${trimEnd(base)}${sep}${name}`
}

export function structureLines(root: string, fullVideos: string | null): StructureLine[] {
  return [
    {
      path: joinPath(root, 'clips'),
      note: '남기기로 한 클립. 자동으로 지워지지 않고, 탐색기에서 폴더를 만들어 마음대로 정리해도 됩니다. (스팀 녹화·영상 파일 구분 없이 자동 보관 폴더에 저장됩니다)',
    },
    {
      path: fullVideos || joinPath(root, 'full_video'),
      note: '게임 전체 영상. 앱이 관리하며 용량 한도(기본 40GB)를 넘으면 오래된 것부터 자동으로 지워집니다.',
    },
  ]
}
