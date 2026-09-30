/** 클립 정리 탭의 순수 계산. 경로는 클립 폴더 기준 `/` 구분 상대 경로다. */

export function parentRel(rel: string): string {
  const cut = rel.lastIndexOf('/')
  return cut < 0 ? '' : rel.slice(0, cut)
}

export function nameOfRel(rel: string): string {
  return rel.slice(rel.lastIndexOf('/') + 1)
}

export function childRel(parent: string, name: string): string {
  return parent ? `${parent}/${name}` : name
}

export function toggle(set: ReadonlySet<string>, key: string): Set<string> {
  const next = new Set(set)
  if (!next.delete(key)) next.add(key)
  return next
}

/** 끌기 시작한 항목이 선택돼 있으면 선택 전체를, 아니면 그 항목만 끈다. */
export function dragItems(selected: ReadonlySet<string>, dragged: string): string[] {
  return selected.has(dragged) ? [...selected] : [dragged]
}

/** 항목들을 `dest` 폴더에 놓을 수 있는지: 이미 그 폴더에 있거나, 자기 자신·자기 안쪽 폴더로는 옮길 수 없다. */
export function canDropOn(items: readonly string[], dest: string): boolean {
  if (items.length === 0) return false
  if (items.some((item) => dest === item || dest.startsWith(`${item}/`))) return false
  return items.some((item) => parentRel(item) !== dest)
}

export function selectionSummary(
  folderKeys: readonly string[],
  clipKeys: readonly string[],
  selected: ReadonlySet<string>,
): string {
  const folders = folderKeys.filter((k) => selected.has(k)).length
  const clips = clipKeys.filter((k) => selected.has(k)).length
  return [folders > 0 ? `폴더 ${folders}개` : '', clips > 0 ? `클립 ${clips}개` : ''].filter(Boolean).join(' · ')
}
